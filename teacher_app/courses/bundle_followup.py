"""Canonical retry/idempotency state for Course Wizard follow-up stages.

The root compatibility adapter still wraps the established upload/link HTTP
handlers.  This module owns workflow lookup, scope validation, stable request
hashes, and follow-up claim/completion persistence.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Any, Mapping, Optional

from teacher_app.common import db as common_db
from teacher_app.common import scope
from teacher_app.common.errors import ApiError
from teacher_app.courses.bundle import WORKFLOW_RE


MIGRATION_ID = "0073-course-bundle-followups"
MAX_FOLLOWUP_INDEX = 499


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _username(user: Optional[Mapping[str, Any]]) -> str:
    return str(
        (user or {}).get("username")
        or (user or {}).get("empId")
        or (user or {}).get("emp_id")
        or ""
    ).strip()


def _row(row) -> dict:
    return dict(row) if row is not None else {}


def _hash_payload(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            dict(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def validate_index(value: Any) -> int:
    try:
        index = int(str(value or "").strip())
    except (TypeError, ValueError) as exc:
        raise ApiError(
            "INVALID_FOLLOWUP_INDEX",
            "教材步驟序號格式不正確。",
            status=400,
        ) from exc
    if index < 0 or index > MAX_FOLLOWUP_INDEX:
        raise ApiError(
            "INVALID_FOLLOWUP_INDEX",
            "教材步驟序號超出允許範圍。",
            status=400,
        )
    return index


def workflow_context(
    user: Optional[Mapping[str, Any]],
    workflow_id: str,
) -> tuple[str, dict]:
    workflow_id = str(workflow_id or "").strip()
    if not WORKFLOW_RE.fullmatch(workflow_id):
        raise ApiError(
            "INVALID_WORKFLOW_ID",
            "建立流程識別碼格式不正確。",
            status=400,
        )

    username = _username(user)
    if not username:
        raise ApiError(
            "LOGIN_REQUIRED",
            "請先登入。",
            status=401,
            extra={"loginRequired": True},
        )

    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT status,course_id,quiz_category_id,training_area,group_key "
            f"FROM course_bundle_requests WHERE username={ph} AND workflow_id={ph}",
            (username, workflow_id),
        ).fetchone()
    return username, _row(row)


def validate_bundle_target(
    bundle: Mapping[str, Any],
    *,
    course_id: str,
    group: str,
    area: str,
    category: str,
) -> None:
    if not bundle or str(bundle.get("status") or "") != "completed":
        raise ApiError(
            "BUNDLE_NOT_READY",
            "找不到已完成的課程建立流程，請先完成課程建立。",
            status=409,
        )
    if str(bundle.get("course_id") or "") != str(course_id or ""):
        raise ApiError(
            "FOLLOWUP_BUNDLE_MISMATCH",
            "教材操作的課程與原建立流程不一致。",
            status=409,
        )

    normalized_group = scope.normalize_group(group or scope.DEFAULT_GROUP)
    normalized_area = scope.normalize_area(area or scope.DEFAULT_TRAINING_AREA)
    if (
        str(bundle.get("group_key") or "") != normalized_group
        or str(bundle.get("training_area") or "") != normalized_area
    ):
        raise ApiError(
            "FOLLOWUP_SCOPE_MISMATCH",
            "教材操作的組別或訓練區與原建立流程不一致。",
            status=409,
        )

    expected_category = str(bundle.get("quiz_category_id") or "")
    if expected_category and str(category or "") != expected_category:
        raise ApiError(
            "FOLLOWUP_EXAM_MISMATCH",
            "教材操作的考卷關聯與原建立流程不一致。",
            status=409,
        )


def upload_claim(
    *,
    workflow_id: str,
    index: int,
    course_id: str,
    category: str,
    group: str,
    area: str,
    title: str,
    material_type: str,
    original_name: str,
    file_size: str,
    last_modified: str,
) -> tuple[str, str]:
    payload = {
        "workflowId": workflow_id,
        "index": index,
        "courseId": course_id,
        "category": category,
        "group": scope.normalize_group(group),
        "area": scope.normalize_area(area),
        "title": str(title or "").strip(),
        "materialType": str(material_type or "auto").strip(),
        "originalName": str(original_name or ""),
        "fileSize": str(file_size or "").strip(),
        "lastModified": str(last_modified or "").strip(),
    }
    return f"upload:{index}", _hash_payload(payload)


def link_claim(
    *,
    workflow_id: str,
    material_id: str,
    course_id: str,
    category: str,
    group: str,
    area: str,
) -> tuple[str, str]:
    payload = {
        "workflowId": workflow_id,
        "materialId": str(material_id),
        "courseId": course_id,
        "category": category,
        "group": scope.normalize_group(group),
        "area": scope.normalize_area(area),
    }
    return f"link:{material_id}", _hash_payload(payload)


def claim(
    *,
    username: str,
    workflow_id: str,
    item_key: str,
    kind_name: str,
    request_hash: str,
) -> tuple[bool, dict]:
    now = _now()
    params = (
        username,
        workflow_id,
        item_key,
        kind_name,
        request_hash,
        "processing",
        0,
        "{}",
        now,
        now,
    )
    with common_db.transaction() as (conn, kind):
        if kind == "postgres":
            cur = conn.execute(
                "INSERT INTO course_bundle_followups "
                "(username,workflow_id,item_key,kind,request_hash,status,response_status,response_json,created_at,updated_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (username,workflow_id,item_key) DO NOTHING",
                params,
            )
        else:
            cur = conn.execute(
                "INSERT OR IGNORE INTO course_bundle_followups "
                "(username,workflow_id,item_key,kind,request_hash,status,response_status,response_json,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                params,
            )
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT * FROM course_bundle_followups WHERE username={ph} AND workflow_id={ph} AND item_key={ph}",
            (username, workflow_id, item_key),
        ).fetchone()
        return cur.rowcount == 1, _row(row)


def reuse_payload(
    inserted: bool,
    row: Mapping[str, Any],
    request_hash: str,
) -> Optional[tuple[dict, int]]:
    if inserted:
        return None
    if str(row.get("request_hash") or "") != request_hash:
        raise ApiError(
            "FOLLOWUP_KEY_REUSED",
            "此教材步驟識別碼已用於不同內容，請重新開始建立流程。",
            status=409,
        )
    if str(row.get("status") or "") == "completed":
        try:
            payload = json.loads(row.get("response_json") or "{}")
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        payload["reused"] = True
        return payload, 200
    raise ApiError(
        "FOLLOWUP_IN_PROGRESS",
        "此教材步驟仍在處理中，請稍後使用相同建立流程重試。",
        status=409,
    )


def release(
    *,
    username: str,
    workflow_id: str,
    item_key: str,
    request_hash: str,
) -> None:
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        conn.execute(
            f"DELETE FROM course_bundle_followups WHERE username={ph} AND workflow_id={ph} "
            f"AND item_key={ph} AND request_hash={ph} AND status={ph}",
            (username, workflow_id, item_key, request_hash, "processing"),
        )


def complete(
    *,
    username: str,
    workflow_id: str,
    item_key: str,
    request_hash: str,
    status_code: int,
    payload: Mapping[str, Any],
) -> None:
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        conn.execute(
            f"UPDATE course_bundle_followups SET status={ph},response_status={ph},response_json={ph},updated_at={ph} "
            f"WHERE username={ph} AND workflow_id={ph} AND item_key={ph} AND request_hash={ph}",
            (
                "completed",
                int(status_code),
                json.dumps(dict(payload), ensure_ascii=False, separators=(",", ":")),
                _now(),
                username,
                workflow_id,
                item_key,
                request_hash,
            ),
        )
