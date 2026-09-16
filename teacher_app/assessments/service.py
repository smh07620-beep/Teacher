"""Canonical assessment configuration, review and publication behavior."""
from __future__ import annotations

import datetime
import json
import uuid
from typing import Any, Mapping

from teacher_app.common.errors import ApiError


QUESTION_TYPES = ("choice", "multi", "true_false", "fill", "essay", "image", "video")


def _fail(code: str, message: str, status: int = 400, extra: dict | None = None) -> ApiError:
    return ApiError(code, message, status=status, extra=extra or {})


def _draw_rules(value: Any) -> dict:
    rules = value if isinstance(value, dict) else {}
    if rules.get("mode") != "type_quota":
        return {}
    raw = rules.get("quotas", {}) if isinstance(rules.get("quotas", {}), dict) else {}
    quotas = {key: max(0, min(200, int(raw.get(key, 0) or 0))) for key in QUESTION_TYPES}
    return {"mode": "type_quota", "quotas": quotas} if sum(quotas.values()) > 0 else {}


def list_categories(base, group: str | None, area: str, include_inactive: bool) -> list[dict]:
    safe_group = group if group in base.GROUPS else None
    safe_area = base.normalize_area(area or base.DEFAULT_TRAINING_AREA)
    return base.list_quiz_categories_with_counts(
        group_key=safe_group,
        training_area=safe_area,
        include_inactive=include_inactive,
    )


def create_category(base, data: Mapping[str, Any]) -> dict:
    group = base.normalize_group(str(data.get("group", base.DEFAULT_GROUP)))
    area = base.normalize_area(str(data.get("area", base.DEFAULT_TRAINING_AREA)))
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
    course = base.get_course(course_id) if course_id else None
    if not course or course.get("group") != group or course.get("area") != area:
        course_id = ""
    if not title:
        raise _fail("ASSESSMENT_TITLE_REQUIRED", "請輸入頁籤名稱")

    category_id = f"cat-{uuid.uuid4().hex[:12]}"
    conn, kind = base._db_conn()
    ph = "%s" if kind == "postgres" else "?"
    try:
        existing = conn.execute(
            f"SELECT COALESCE(MAX(sort_order), -1) AS m FROM quiz_categories WHERE group_key = {ph}",
            (group,),
        ).fetchone()
        next_order = (existing["m"] if isinstance(existing, dict) else existing[0]) + 1
        date_added = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        values = (
            category_id,
            group,
            area,
            course_id,
            title,
            desc,
            next_order,
            date_added,
            False if kind == "postgres" else 0,
            draw_count,
            passing_score,
            audience,
            json.dumps(draw_rules, ensure_ascii=False),
            "draft",
            "",
            "",
            "",
        )
        if kind == "postgres":
            conn.execute(
                "INSERT INTO quiz_categories (id,group_key,training_area,course_id,title,description,sort_order,date_added,active,draw_count,passing_score,audience,draw_rules,review_status,reviewer_name,reviewed_at,published_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)",
                values,
            )
        else:
            conn.execute(
                "INSERT INTO quiz_categories (id,group_key,training_area,course_id,title,description,sort_order,date_added,active,draw_count,passing_score,audience,draw_rules,review_status,reviewer_name,reviewed_at,published_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                values,
            )
    finally:
        conn.close()
    return base.get_quiz_category(category_id)


def update_category(base, category_id: str, data: Mapping[str, Any]) -> dict:
    entry = base.get_quiz_category(category_id)
    if not entry:
        raise _fail("ASSESSMENT_NOT_FOUND", "找不到此考題頁籤", 404)

    title = str(data.get("title", entry["title"])).strip()[:255]
    desc = str(data.get("desc", entry.get("desc", ""))).strip()[:1000]
    active = bool(data.get("active", entry.get("active", True)))
    review_status = str(data.get("reviewStatus", entry.get("reviewStatus", "approved")) or "draft").lower()
    if review_status not in {"draft", "approved"}:
        review_status = entry.get("reviewStatus", "draft")
    reviewer_name = str(data.get("reviewerName", entry.get("reviewerName", "")) or "").strip()[:100]
    reviewed_at = str(data.get("reviewedAt", entry.get("reviewedAt", "")) or "")[:80]
    published_at = str(data.get("publishedAt", entry.get("publishedAt", "")) or "")[:80]
    blind_mode = bool(data.get("blindMode", entry.get("blindMode", False)))
    audience = str(data.get("audience", entry.get("audience", ""))).strip()[:200]
    course_id = str(data.get("courseId", entry.get("courseId", ""))).strip()[:100]
    course = base.get_course(course_id) if course_id else None
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

    conn, kind = base._db_conn()
    try:
        values = (
            title,
            desc,
            active if kind == "postgres" else int(active),
            blind_mode if kind == "postgres" else int(blind_mode),
            draw_count,
            passing_score,
            audience,
            course_id,
            json.dumps(draw_rules, ensure_ascii=False),
            review_status,
            reviewer_name,
            reviewed_at,
            published_at,
            category_id,
        )
        if kind == "postgres":
            conn.execute(
                "UPDATE quiz_categories SET title=%s, description=%s, active=%s, blind_mode=%s, draw_count=%s, passing_score=%s, audience=%s, course_id=%s, draw_rules=%s::jsonb, review_status=%s, reviewer_name=%s, reviewed_at=%s, published_at=%s WHERE id=%s",
                values,
            )
        else:
            conn.execute(
                "UPDATE quiz_categories SET title=?, description=?, active=?, blind_mode=?, draw_count=?, passing_score=?, audience=?, course_id=?, draw_rules=?, review_status=?, reviewer_name=?, reviewed_at=?, published_at=? WHERE id=?",
                values,
            )
        if config_changed:
            ph = "%s" if kind == "postgres" else "?"
            conn.execute(
                f"UPDATE quiz_categories SET publication_id='', publication_hash='' WHERE id={ph}",
                (category_id,),
            )
    finally:
        conn.close()
    return {"ok": True}


def review_category(base, category_id: str, data: Mapping[str, Any]) -> dict:
    entry = base.get_quiz_category(category_id)
    if not entry:
        raise _fail("ASSESSMENT_NOT_FOUND", "找不到此考卷", 404)
    reviewer = str(data.get("reviewerName", "")).strip()[:100]
    if not reviewer:
        raise _fail("REVIEWER_REQUIRED", "審核前請填寫審核者姓名")
    questions = base.list_quiz_questions(category_id, include_inactive=False)
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
    conn, kind = base._db_conn()
    ph = "%s" if kind == "postgres" else "?"
    try:
        conn.execute(
            f"UPDATE quiz_categories SET review_status={ph}, reviewer_name={ph}, reviewed_at={ph}, active={ph} WHERE id={ph}",
            ("approved", reviewer, now, False if kind == "postgres" else 0, category_id),
        )
    finally:
        conn.close()
    return {
        "ok": True,
        "reviewStatus": "approved",
        "reviewerName": reviewer,
        "reviewedAt": now,
        "questionCount": len(questions),
    }


def list_publications(base, category_id: str) -> list[dict]:
    if not base.get_quiz_category(category_id):
        raise _fail("ASSESSMENT_NOT_FOUND", "找不到此考卷", 404)
    conn, kind = base._db_conn()
    ph = "%s" if kind == "postgres" else "?"
    try:
        rows = conn.execute(
            f"SELECT id,created_at,reviewer_name,snapshot_hash FROM quiz_publications WHERE quiz_category_id={ph} ORDER BY created_at DESC LIMIT 30",
            (category_id,),
        ).fetchall()
        return [
            {
                "id": dict(row).get("id", ""),
                "createdAt": dict(row).get("created_at", ""),
                "reviewerName": dict(row).get("reviewer_name", ""),
                "snapshotHash": dict(row).get("snapshot_hash", ""),
            }
            for row in rows
        ]
    finally:
        conn.close()


def publish_category(base, category_id: str) -> dict:
    entry = base.get_quiz_category(category_id)
    if not entry:
        raise _fail("ASSESSMENT_NOT_FOUND", "找不到此考卷", 404)
    if entry.get("reviewStatus") != "approved":
        raise _fail("ASSESSMENT_NOT_REVIEWED", "此考卷尚未完成審核，不能發布", 409)
    if not base.list_quiz_questions(category_id, include_inactive=False):
        raise _fail("ASSESSMENT_EMPTY", "此考卷沒有啟用中的題目，不能發布", 409)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    snapshot, snapshot_hash, publication_id = base._quiz_publication_snapshot(category_id)
    conn, kind = base._db_conn()
    try:
        if kind == "postgres":
            with conn.transaction():
                conn.execute(
                    "INSERT INTO quiz_publications (id,quiz_category_id,created_at,reviewer_name,snapshot_hash,snapshot) VALUES (%s,%s,%s,%s,%s,%s::jsonb)",
                    (publication_id, category_id, now, entry.get("reviewerName", ""), snapshot_hash, json.dumps(snapshot, ensure_ascii=False)),
                )
                conn.execute(
                    "UPDATE quiz_categories SET active=TRUE, published_at=%s, publication_id=%s, publication_hash=%s WHERE id=%s",
                    (now, publication_id, snapshot_hash, category_id),
                )
        else:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO quiz_publications (id,quiz_category_id,created_at,reviewer_name,snapshot_hash,snapshot) VALUES (?,?,?,?,?,?)",
                (publication_id, category_id, now, entry.get("reviewerName", ""), snapshot_hash, json.dumps(snapshot, ensure_ascii=False)),
            )
            conn.execute(
                "UPDATE quiz_categories SET active=1, published_at=?, publication_id=?, publication_hash=? WHERE id=?",
                (now, publication_id, snapshot_hash, category_id),
            )
            conn.execute("COMMIT")
    except Exception:
        if kind != "postgres":
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
        raise
    finally:
        conn.close()
    return {
        "ok": True,
        "active": True,
        "publishedAt": now,
        "publicationId": publication_id,
        "publicationHash": snapshot_hash,
        "snapshotQuestionCount": len(snapshot.get("questions") or []),
    }


def category_materials(base, category_id: str) -> dict:
    category = base.get_quiz_category(category_id)
    if not category:
        raise _fail("ASSESSMENT_NOT_FOUND", "找不到此考卷", 404)
    items = []
    for material in base.list_uploaded_materials(include_inactive=True):
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
    category = base.get_quiz_category(category_id)
    if not category:
        raise _fail("ASSESSMENT_NOT_FOUND", "找不到此考卷", 404)
    raw = data.get("materialIds") or []
    if not isinstance(raw, list):
        raise _fail("MATERIAL_IDS_INVALID", "materialIds 必須是陣列")
    allowed = {
        material.get("id")
        for material in base.list_uploaded_materials(include_inactive=True)
        if material.get("group") == category.get("group") and material.get("area") == category.get("area")
    }
    selected: list[str] = []
    for value in raw:
        material_id = str(value).strip()
        if material_id in allowed and material_id not in selected:
            selected.append(material_id)
    conn, kind = base._db_conn()
    try:
        if kind == "postgres":
            conn.execute("UPDATE materials SET category='' WHERE category=%s", (category_id,))
            if selected:
                placeholders = ",".join(["%s"] * len(selected))
                conn.execute(
                    f"UPDATE materials SET category=%s WHERE id IN ({placeholders}) AND group_key=%s AND training_area=%s",
                    tuple([category_id] + selected + [category.get("group"), category.get("area")]),
                )
        else:
            conn.execute("UPDATE materials SET category='' WHERE category=?", (category_id,))
            if selected:
                placeholders = ",".join(["?"] * len(selected))
                conn.execute(
                    f"UPDATE materials SET category=? WHERE id IN ({placeholders}) AND group_key=? AND training_area=?",
                    tuple([category_id] + selected + [category.get("group"), category.get("area")]),
                )
    finally:
        conn.close()
    return {"ok": True, "linkedIds": selected, "linked": len(selected)}


def delete_category(base, category_id: str) -> dict:
    if not base.get_quiz_category(category_id):
        raise _fail("ASSESSMENT_NOT_FOUND", "找不到此考題頁籤", 404)
    conn, kind = base._db_conn()
    try:
        if kind == "postgres":
            conn.execute("DELETE FROM quiz_questions WHERE quiz_category_id=%s", (category_id,))
            conn.execute("DELETE FROM quiz_categories WHERE id=%s", (category_id,))
            conn.execute("UPDATE materials SET category='' WHERE category=%s", (category_id,))
        else:
            conn.execute("DELETE FROM quiz_questions WHERE quiz_category_id=?", (category_id,))
            conn.execute("DELETE FROM quiz_categories WHERE id=?", (category_id,))
            conn.execute("UPDATE materials SET category='' WHERE category=?", (category_id,))
    finally:
        conn.close()
    return {"ok": True}
