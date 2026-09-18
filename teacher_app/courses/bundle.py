"""Canonical Course Wizard bundle creation.

This module owns retry-safe/idempotent creation of one course plus an optional
draft assessment.  The root ``course_bundle_72`` module keeps only the legacy
HTTP route, capability gates, and response projection compatibility.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import uuid
from typing import Any, Mapping, Optional

from teacher_app.common import db as common_db
from teacher_app.common import scope
from teacher_app.common.errors import ApiError
from teacher_app.assessments import repository as assessment_repository
from teacher_app.courses import repository as course_repository


MIGRATION_ID = "0072-course-bundle-idempotency"
WORKFLOW_RE = re.compile(r"^[A-Za-z0-9._:-]{12,120}$")
EXAM_MODES = {"later", "bank", "ai", "blueprint"}


def _row_dict(row) -> dict:
    return dict(row) if row is not None else {}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _display_time() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def _username(user: Optional[Mapping[str, Any]]) -> str:
    return str(
        (user or {}).get("username")
        or (user or {}).get("empId")
        or (user or {}).get("emp_id")
        or ""
    ).strip()


def _request_core(data: Mapping[str, Any]):
    workflow_id = str(data.get("workflowId") or "").strip()
    if not WORKFLOW_RE.fullmatch(workflow_id):
        raise ApiError(
            "INVALID_WORKFLOW_ID",
            "建立流程識別碼格式不正確，請重新開始建立流程。",
            status=400,
        )

    area = scope.normalize_area(data.get("area") or scope.DEFAULT_TRAINING_AREA)
    group = scope.normalize_group(data.get("group") or scope.DEFAULT_GROUP)
    title = str(data.get("title") or "").strip()[:255]
    desc = str(data.get("desc") or "").strip()[:2000]
    exam_mode = str(data.get("examMode") or "later").strip().lower()
    exam_title = str(data.get("examTitle") or "").strip()[:255]

    if not title:
        raise ApiError("COURSE_TITLE_REQUIRED", "請輸入課程名稱", status=400)
    if exam_mode not in EXAM_MODES:
        raise ApiError("INVALID_EXAM_MODE", "不支援的考卷建立模式", status=400)
    if exam_mode != "later" and not exam_title:
        raise ApiError(
            "EXAM_TITLE_REQUIRED",
            "請輸入考卷名稱，或改選「稍後建立」。",
            status=400,
        )

    core = {
        "area": area,
        "group": group,
        "title": title,
        "desc": desc,
        "examMode": exam_mode,
        "examTitle": exam_title if exam_mode != "later" else "",
    }
    digest = hashlib.sha256(
        json.dumps(
            core,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return workflow_id, core, digest


def _bounded_count(value: Any) -> int:
    try:
        return max(0, min(500, int(value or 0)))
    except (TypeError, ValueError) as exc:
        raise ApiError(
            "INVALID_MATERIAL_COUNT",
            "教材數量格式不正確。",
            status=400,
        ) from exc


def _insert_claim(
    conn,
    kind: str,
    *,
    username: str,
    workflow_id: str,
    request_hash: str,
    area: str,
    group: str,
    now: str,
) -> bool:
    params = (
        username,
        workflow_id,
        request_hash,
        area,
        group,
        "creating",
        "",
        "",
        "{}",
        now,
        now,
    )
    if kind == "postgres":
        cur = conn.execute(
            "INSERT INTO course_bundle_requests "
            "(username,workflow_id,request_hash,training_area,group_key,status,course_id,quiz_category_id,result_json,created_at,updated_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (username,workflow_id) DO NOTHING",
            params,
        )
    else:
        cur = conn.execute(
            "INSERT OR IGNORE INTO course_bundle_requests "
            "(username,workflow_id,request_hash,training_area,group_key,status,course_id,quiz_category_id,result_json,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            params,
        )
    return cur.rowcount == 1


def _load_claim(conn, kind: str, username: str, workflow_id: str) -> dict:
    ph = common_db.placeholder(kind)
    return _row_dict(
        conn.execute(
            f"SELECT * FROM course_bundle_requests WHERE username={ph} AND workflow_id={ph}",
            (username, workflow_id),
        ).fetchone()
    )


def _create_course(conn, kind: str, core: Mapping[str, Any]) -> str:
    course_id = f"course-{uuid.uuid4().hex[:12]}"
    order = course_repository.next_sort_order_on_connection(
        conn, kind, area=core["area"], group=core["group"]
    )
    course_repository.insert_course_on_connection(
        conn,
        kind,
        course_id=course_id,
        area=core["area"],
        group=core["group"],
        title=core["title"],
        description=core["desc"],
        sort_order=order,
        date_added=_display_time(),
        active=True,
    )
    return course_id


def _create_exam(
    conn,
    kind: str,
    core: Mapping[str, Any],
    course_id: str,
) -> str:
    if core["examMode"] == "later":
        return ""

    category_id = f"cat-{uuid.uuid4().hex[:12]}"
    order = assessment_repository.next_category_sort_order_on_connection(
        conn,
        kind,
        group=core["group"],
        training_area=core["area"],
    )
    assessment_repository.insert_category_on_connection(conn, kind, {
        "id": category_id,
        "group_key": core["group"],
        "training_area": core["area"],
        "course_id": course_id,
        "title": core["examTitle"],
        "description": f"{core['title']} 課後評量",
        "sort_order": order,
        "date_added": _display_time(),
        "active": False,
        "draw_count": 0,
        "passing_score": 80,
        "audience": "",
        "draw_rules": json.dumps({}, ensure_ascii=False),
        "review_status": "draft",
        "reviewer_name": "",
        "reviewed_at": "",
        "published_at": "",
    })
    return category_id


def _stored_result(
    workflow_id: str,
    core: Mapping[str, Any],
    course_id: str,
    category_id: str,
    material_count: int,
    upload_count: int,
) -> dict:
    return {
        "ok": True,
        "workflowId": workflow_id,
        "status": "completed",
        "reused": False,
        "course": {
            "id": course_id,
            "area": core["area"],
            "group": core["group"],
            "title": core["title"],
            "desc": core["desc"],
            "active": True,
        },
        "quizCategory": (
            {
                "id": category_id,
                "group": core["group"],
                "area": core["area"],
                "courseId": course_id,
                "title": core["examTitle"],
                "desc": f"{core['title']} 課後評量",
                "active": False,
                "reviewStatus": "draft",
            }
            if category_id
            else None
        ),
        "stages": {
            "course": "created",
            "exam": "created" if category_id else "skipped",
            "materials": "pending-client" if material_count else "skipped",
            "uploads": "pending-background" if upload_count else "skipped",
        },
    }


def _as_reused(result: Mapping[str, Any]) -> dict:
    output = dict(result or {})
    output["reused"] = True
    stages = dict(output.get("stages") or {})
    stages["course"] = "reused"
    if output.get("quizCategory"):
        stages["exam"] = "reused"
    output["stages"] = stages
    return output


def create_bundle(
    user: Optional[Mapping[str, Any]],
    data: Mapping[str, Any],
) -> tuple[dict, int]:
    """Create or reuse one atomic Course Wizard bundle."""
    if not isinstance(data, Mapping):
        raise ApiError("INVALID_PAYLOAD", "請提供有效的建立資料。", status=400)

    username = _username(user)
    if not username:
        raise ApiError(
            "LOGIN_REQUIRED",
            "請先登入。",
            status=401,
            extra={"loginRequired": True},
        )

    workflow_id, core, request_hash = _request_core(data)
    material_count = _bounded_count(data.get("existingMaterialCount"))
    upload_count = _bounded_count(data.get("uploadCount"))
    now = _now()

    with common_db.transaction() as (conn, kind):
        inserted = _insert_claim(
            conn,
            kind,
            username=username,
            workflow_id=workflow_id,
            request_hash=request_hash,
            area=core["area"],
            group=core["group"],
            now=now,
        )
        claim = _load_claim(conn, kind, username, workflow_id)
        if not claim:
            raise RuntimeError("無法建立流程紀錄")

        if claim.get("request_hash") != request_hash:
            raise ApiError(
                "IDEMPOTENCY_KEY_REUSED",
                "此建立流程識別碼已用於不同內容，請重新開始建立流程。",
                status=409,
            )

        if not inserted:
            if claim.get("status") == "completed":
                stored = json.loads(claim.get("result_json") or "{}")
                return _as_reused(stored), 200
            raise ApiError(
                "WORKFLOW_IN_PROGRESS",
                "此建立流程仍在處理中，請稍後使用相同流程識別碼重試。",
                status=409,
            )

        course_id = _create_course(conn, kind, core)
        category_id = _create_exam(conn, kind, core, course_id)
        result = _stored_result(
            workflow_id,
            core,
            course_id,
            category_id,
            material_count,
            upload_count,
        )
        ph = common_db.placeholder(kind)
        conn.execute(
            f"UPDATE course_bundle_requests SET status={ph},course_id={ph},quiz_category_id={ph},result_json={ph},updated_at={ph} "
            f"WHERE username={ph} AND workflow_id={ph}",
            (
                "completed",
                course_id,
                category_id,
                json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                _now(),
                username,
                workflow_id,
            ),
        )
        return result, 201
