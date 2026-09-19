"""Canonical assessment configuration, review and publication behavior."""
from __future__ import annotations

import copy
import datetime
import hashlib
import json
import threading
import time
import uuid
from typing import Any, Mapping

from teacher_app.common import db as common_db
from teacher_app.common import scope
from teacher_app.common.errors import ApiError
from teacher_app.courses import repository as course_repository
from teacher_app.materials import repository as materials_repository
from teacher_app.assessments import repository


QUESTION_TYPES = ("choice", "multi", "true_false", "fill", "essay", "image", "video")

# Render currently runs one Gunicorn worker with multiple threads.  Opening the
# Teacher Content Studio first reads the public exam list and then the admin
# workspace used to read the same rows again through a second Supabase
# connection.  Keep a very short, process-local snapshot of the *full* list so
# the public read can warm the immediately-following admin read.  All mutations
# below invalidate this cache; question counts can be at most this TTL stale and
# are refreshed automatically on the next read.
_CATEGORY_LIST_CACHE_TTL_SECONDS = 15.0
_CATEGORY_LIST_CACHE: dict[tuple[int, str, str], tuple[float, list[dict]]] = {}
_CATEGORY_LIST_CACHE_LOCK = threading.Lock()


def _fail(code: str, message: str, status: int = 400, extra: dict | None = None) -> ApiError:
    return ApiError(code, message, status=status, extra=extra or {})


def _compat_actor_label(base) -> str:
    """Resolve only a server-bound compatibility actor, never payload identity."""
    resolver = getattr(base, "_current_user", None)
    user = resolver() if callable(resolver) else None
    user = user if isinstance(user, Mapping) else {}
    return str(user.get("name") or user.get("username") or "").strip()[:100]


def _draw_rules(value: Any) -> dict:
    rules = value if isinstance(value, dict) else {}
    if rules.get("mode") != "type_quota":
        return {}
    raw = rules.get("quotas", {}) if isinstance(rules.get("quotas", {}), dict) else {}
    quotas = {key: max(0, min(200, int(raw.get(key, 0) or 0))) for key in QUESTION_TYPES}
    return {"mode": "type_quota", "quotas": quotas} if sum(quotas.values()) > 0 else {}


def _category_cache_key(base, group: str | None, area: str) -> tuple[int, str, str]:
    return (id(base), str(group or ""), str(area or ""))


def _clear_category_list_cache(base=None, group: str | None = None, area: str | None = None) -> None:
    with _CATEGORY_LIST_CACHE_LOCK:
        if base is None and group is None and area is None:
            _CATEGORY_LIST_CACHE.clear()
            return
        base_id = id(base) if base is not None else None
        wanted_group = None if group is None else str(group)
        wanted_area = None if area is None else str(area)
        for key in list(_CATEGORY_LIST_CACHE):
            key_base, key_group, key_area = key
            if base_id is not None and key_base != base_id:
                continue
            if wanted_group is not None and key_group != wanted_group:
                continue
            if wanted_area is not None and key_area != wanted_area:
                continue
            _CATEGORY_LIST_CACHE.pop(key, None)


def list_categories(base, group: str | None, area: str, include_inactive: bool) -> list[dict]:
    safe_group = scope.normalize_group(group) if group else None
    safe_area = scope.normalize_area(area or scope.DEFAULT_TRAINING_AREA)
    key = _category_cache_key(base, safe_group, safe_area)
    now = time.monotonic()

    with _CATEGORY_LIST_CACHE_LOCK:
        cached = _CATEGORY_LIST_CACHE.get(key)
        full_list = copy.deepcopy(cached[1]) if cached and now - cached[0] < _CATEGORY_LIST_CACHE_TTL_SECONDS else None

    if full_list is None:
        # Always fetch the full list once.  The public endpoint filters inactive
        # rows below, while the admin endpoint can reuse the same DB result a
        # moment later instead of opening another Supabase connection.
        full_list = repository.list_categories_with_counts(
            group_key=safe_group,
            training_area=safe_area,
            include_inactive=True,
        )
        with _CATEGORY_LIST_CACHE_LOCK:
            _CATEGORY_LIST_CACHE[key] = (time.monotonic(), copy.deepcopy(full_list))

    if include_inactive:
        return full_list
    return [item for item in full_list if bool(item.get("active"))]


def create_category(base, data: Mapping[str, Any]) -> dict:
    group = scope.normalize_group(str(data.get("group", scope.DEFAULT_GROUP)))
    area = scope.normalize_area(str(data.get("area", scope.DEFAULT_TRAINING_AREA)))
    title = str(data.get("title", "")).strip()[:255]
    desc = str(data.get("desc", "")).strip()[:1000]
    audience = str(data.get("audience", "")).strip()[:200]
    try:
        draw_count = max(0, int(data.get("drawCount", 0) or 0))
    except (TypeError, ValueError):
        draw_count = 0
    try:
        passing_score = max(1, min(100, int(data.get("passingScore", 80) or 80)))
    except (TypeError, ValueError):
        passing_score = 80
    try:
        draw_rules = _draw_rules(data.get("drawRules", {}))
    except (TypeError, ValueError):
        draw_rules = {}
    course_id = str(data.get("courseId", "")).strip()
    course = course_repository.get_course(course_id) if course_id else None
    if not course or course.get("group") != group or course.get("area") != area:
        course_id = ""
    if not title:
        raise _fail("ASSESSMENT_TITLE_REQUIRED", "請輸入頁籤名稱")

    category_id = f"cat-{uuid.uuid4().hex[:12]}"
    created = repository.create_category({
        "id": category_id,
        "group_key": group,
        "training_area": area,
        "course_id": course_id,
        "title": title,
        "description": desc,
        "date_added": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "active": False,
        "draw_count": draw_count,
        "passing_score": passing_score,
        "audience": audience,
        "draw_rules": json.dumps(draw_rules, ensure_ascii=False),
        "review_status": "draft",
        "reviewer_name": "",
        "reviewed_at": "",
        "published_at": "",
    })
    _clear_category_list_cache(base, group, area)
    return created or repository.get_category_full(category_id)


def update_category(base, category_id: str, data: Mapping[str, Any]) -> dict:
    entry = repository.get_category_full(category_id)
    if not entry:
        raise _fail("ASSESSMENT_NOT_FOUND", "找不到此考題頁籤", 404)

    title = str(data.get("title", entry["title"])).strip()[:255]
    desc = str(data.get("desc", entry.get("desc", ""))).strip()[:1000]
    # Review/publication state is workflow-owned.  A settings PATCH may retain
    # the current state or invalidate it through a content change, but it may
    # never approve/publish itself from browser-supplied workflow fields.
    active = bool(entry.get("active", False))
    review_status = str(entry.get("reviewStatus", "draft") or "draft").lower()
    reviewer_name = str(entry.get("reviewerName", "") or "").strip()[:100]
    reviewed_at = str(entry.get("reviewedAt", "") or "")[:80]
    published_at = str(entry.get("publishedAt", "") or "")[:80]
    blind_mode = bool(data.get("blindMode", entry.get("blindMode", False)))
    audience = str(data.get("audience", entry.get("audience", ""))).strip()[:200]
    course_id = str(data.get("courseId", entry.get("courseId", ""))).strip()[:100]
    course = course_repository.get_course(course_id) if course_id else None
    if not course or course.get("group") != entry.get("group") or course.get("area") != entry.get("area"):
        course_id = ""
    try:
        draw_count = max(0, int(data.get("drawCount", entry.get("drawCount", 0)) or 0))
    except (TypeError, ValueError):
        draw_count = max(0, int(entry.get("drawCount", 0) or 0))
    try:
        passing_score = max(1, min(100, int(data.get("passingScore", entry.get("passingScore", 80)) or 80)))
    except (TypeError, ValueError):
        passing_score = max(1, min(100, int(entry.get("passingScore", 80) or 80)))
    try:
        draw_rules = _draw_rules(data.get("drawRules", entry.get("drawRules", {})))
    except (TypeError, ValueError):
        draw_rules = entry.get("drawRules", {}) or {}

    config_changed = any(
        [
            title != entry.get("title", ""),
            desc != entry.get("desc", ""),
            blind_mode != bool(entry.get("blindMode", False)),
            draw_count != int(entry.get("drawCount", 0) or 0),
            passing_score != int(entry.get("passingScore", 80) or 80),
            audience != str(entry.get("audience", "") or ""),
            course_id != str(entry.get("courseId", "") or ""),
            draw_rules != (entry.get("drawRules", {}) or {}),
        ]
    )
    if config_changed:
        review_status, reviewer_name, reviewed_at, published_at, active = "draft", "", "", "", False
    elif active and review_status != "approved":
        raise _fail("ASSESSMENT_NOT_REVIEWED", "此考卷尚未完成審核，請先執行『審核』再發布。", 409)

    repository.update_category(category_id, {
        "title": title,
        "description": desc,
        "active": active,
        "blind_mode": blind_mode,
        "draw_count": draw_count,
        "passing_score": passing_score,
        "audience": audience,
        "course_id": course_id,
        "draw_rules": json.dumps(draw_rules, ensure_ascii=False),
        "review_status": review_status,
        "reviewer_name": reviewer_name,
        "reviewed_at": reviewed_at,
        "published_at": published_at,
    }, reset_publication=config_changed)
    _clear_category_list_cache(base, entry.get("group"), entry.get("area"))
    return {
        "ok": True,
        "active": active,
        "reviewStatus": review_status,
        "reviewerName": reviewer_name,
        "reviewedAt": reviewed_at,
        "publishedAt": published_at,
    }


def review_category(
    base,
    category_id: str,
    _data: Mapping[str, Any] | None = None,
    *,
    reviewer: str = "",
) -> dict:
    entry = repository.get_category_full(category_id)
    if not entry:
        raise _fail("ASSESSMENT_NOT_FOUND", "找不到此考卷", 404)
    reviewer = str(reviewer or _compat_actor_label(base)).strip()[:100]
    if not reviewer:
        raise _fail("REVIEWER_REQUIRED", "無法確認目前登入的審核者", 401)
    questions = repository.list_questions(category_id, include_inactive=False)
    if not questions:
        raise _fail("ASSESSMENT_EMPTY", "此考卷沒有啟用中的題目，無法完成審核", 409)
    invalid: list[str] = []
    for index, question in enumerate(questions, start=1):
        if not str(question.get("question", "")).strip():
            invalid.append(f"第 {index} 題題幹空白")
        if question.get("questionType") in {"choice", "multi", "image", "video", "true_false"} and len(question.get("options") or []) < 2:
            invalid.append(f"第 {index} 題選項不足")
        if question.get("questionType") == "essay" and not str(question.get("explanation", "")).strip():
            invalid.append(f"第 {index} 題問答題缺少評分參考")
    if invalid:
        raise _fail("ASSESSMENT_REVIEW_FAILED", "題目審核未通過", 409, {"issues": invalid[:20]})
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    repository.mark_category_reviewed(category_id, reviewer=reviewer, reviewed_at=now)
    _clear_category_list_cache(base, entry.get("group"), entry.get("area"))
    return {
        "ok": True,
        "reviewStatus": "approved",
        "reviewerName": reviewer,
        "reviewedAt": now,
        "questionCount": len(questions),
    }


def list_publications(base, category_id: str) -> list[dict]:
    if not repository.get_category_full(category_id):
        raise _fail("ASSESSMENT_NOT_FOUND", "找不到此考卷", 404)
    return [
        {
            "id": row.get("id", ""),
            "createdAt": row.get("created_at", ""),
            "reviewerName": row.get("reviewer_name", ""),
            "snapshotHash": row.get("snapshot_hash", ""),
        }
        for row in repository.list_publications(category_id)
    ]


def publication_snapshot(category_id: str, *, published_by: str = "") -> tuple[dict, str, str]:
    category = repository.get_category_full(category_id)
    if not category:
        raise ValueError("找不到此考卷")
    questions = repository.list_questions(category_id, include_inactive=False)
    snapshot = {
        "schemaVersion": 1,
        "category": {
            "id": category.get("id"),
            "title": category.get("title"),
            "desc": category.get("desc", ""),
            "group": category.get("group"),
            "area": category.get("area"),
            "courseId": category.get("courseId", ""),
            "blindMode": bool(category.get("blindMode", False)),
            "drawCount": int(category.get("drawCount", 0) or 0),
            "passingScore": int(category.get("passingScore", 80) or 80),
            "audience": category.get("audience", ""),
            "drawRules": category.get("drawRules", {}) or {},
            "reviewerName": category.get("reviewerName", ""),
            "reviewedAt": category.get("reviewedAt", ""),
            "publishedBy": str(published_by or "")[:100],
        },
        "questions": [
            {
                "id": question.get("id"),
                "tag": question.get("tag", ""),
                "question": question.get("question", ""),
                "questionType": question.get("questionType", "choice"),
                "imageUrl": question.get("imageUrl", ""),
                "options": question.get("options", []) or [],
                "correct": question.get("correct", 0),
                "answerConfig": question.get("answerConfig", {}) or {},
                "explanation": question.get("explanation", ""),
                "difficulty": question.get("difficulty", "standard"),
                "sortOrder": int(question.get("sortOrder", 0) or 0),
            }
            for question in questions
        ],
    }
    canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    publication_id = f"pub-{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S')}-{digest[:10]}"
    return snapshot, digest, publication_id


def publish_category(base, category_id: str, *, publisher: str = "") -> dict:
    entry = repository.get_category_full(category_id)
    if not entry:
        raise _fail("ASSESSMENT_NOT_FOUND", "找不到此考卷", 404)
    if entry.get("reviewStatus") != "approved":
        raise _fail("ASSESSMENT_NOT_REVIEWED", "此考卷尚未完成審核，不能發布", 409)
    if not repository.list_questions(category_id, include_inactive=False):
        raise _fail("ASSESSMENT_EMPTY", "此考卷沒有啟用中的題目，不能發布", 409)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    publisher = str(publisher or _compat_actor_label(base)).strip()[:100]
    if not publisher:
        raise _fail("PUBLISHER_REQUIRED", "無法確認目前登入的發布者", 401)
    snapshot, snapshot_hash, publication_id = publication_snapshot(
        category_id,
        published_by=publisher,
    )
    repository.publish_category(
        category_id,
        publication_id=publication_id,
        created_at=now,
        reviewer_name=entry.get("reviewerName", ""),
        snapshot_hash=snapshot_hash,
        snapshot=snapshot,
    )
    _clear_category_list_cache(base, entry.get("group"), entry.get("area"))
    return {
        "ok": True,
        "active": True,
        "publishedAt": now,
        "publicationId": publication_id,
        "publicationHash": snapshot_hash,
        "snapshotQuestionCount": len(snapshot.get("questions") or []),
        "publishedBy": publisher,
    }


def category_materials(base, category_id: str) -> dict:
    category = repository.get_category_full(category_id)
    if not category:
        raise _fail("ASSESSMENT_NOT_FOUND", "找不到此考卷", 404)
    items = []
    for material in materials_repository.list_uploaded_materials(base, include_inactive=True):
        if material.get("group") == category.get("group") and material.get("area") == category.get("area"):
            items.append(
                {
                    "id": material.get("id"),
                    "title": material.get("title") or material.get("filename"),
                    "filename": material.get("filename", ""),
                    "materialType": material.get("materialType", "standard"),
                    "courseId": material.get("courseId", ""),
                    "category": material.get("category", ""),
                    "linked": material.get("category") == category_id,
                    "active": material.get("active", True),
                }
            )
    items.sort(key=lambda item: (not item["linked"], str(item.get("title", "")).lower()))
    return {"categoryId": category_id, "items": items}


def update_category_materials(base, category_id: str, data: Mapping[str, Any]) -> dict:
    category = repository.get_category_full(category_id)
    if not category:
        raise _fail("ASSESSMENT_NOT_FOUND", "找不到此考卷", 404)
    raw = data.get("materialIds") or []
    if not isinstance(raw, list):
        raise _fail("MATERIAL_IDS_INVALID", "materialIds 必須是陣列")
    allowed = {
        material.get("id")
        for material in materials_repository.list_uploaded_materials(base, include_inactive=True)
        if material.get("group") == category.get("group") and material.get("area") == category.get("area")
    }
    selected: list[str] = []
    for value in raw:
        material_id = str(value).strip()
        if material_id in allowed and material_id not in selected:
            selected.append(material_id)
    materials_repository.replace_category_assignments(
        category_id,
        selected,
        group_key=category.get("group"),
        training_area=category.get("area"),
    )
    return {"ok": True, "linkedIds": selected, "linked": len(selected)}


def delete_category(base, category_id: str) -> dict:
    entry = repository.get_category_full(category_id)
    if not entry:
        raise _fail("ASSESSMENT_NOT_FOUND", "找不到此考題頁籤", 404)
    with common_db.transaction() as (conn, kind):
        repository.delete_category_on_connection(conn, kind, category_id)
        materials_repository.clear_category_assignment(conn, kind, category_id)
    _clear_category_list_cache(base, entry.get("group"), entry.get("area"))
    return {"ok": True}
