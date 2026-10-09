"""Who may see and take an exam.

An exam with no assignee rows keeps the historical behaviour (everyone in scope
may see it).  Once at least one row exists the exam is restricted to the listed
people / groups, plus exam managers.  Enforcement lives on the server:
``filter_for_user`` for listings and ``assert_can_take`` when an attempt starts.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Iterable, Mapping

from teacher_app.common import db as common_db, scope
from teacher_app.common.auth import has_permission
from teacher_app.common.errors import ApiError

TYPES = {"user", "group", "all"}


def _norm(item: Mapping[str, Any]) -> tuple[str, str]:
    kind = str(item.get("type") or item.get("assigneeType") or "").strip().lower()
    key = str(item.get("key") or item.get("assigneeKey") or "").strip()
    if kind not in TYPES:
        raise ApiError("ASSIGNEE_TYPE_INVALID", "不支援的指派對象類型。", 400)
    if kind == "all":
        return "all", ""
    if not key:
        raise ApiError("ASSIGNEE_KEY_REQUIRED", "請選擇指派對象。", 400)
    if kind == "user":
        return "user", key.lower()
    if key not in scope.GROUPS:
        raise ApiError("ASSIGNEE_GROUP_INVALID", "找不到指定的組別。", 400)
    return "group", key


def _table_missing(exc: Exception) -> bool:
    """Only the not-yet-migrated case is tolerated; any other error propagates."""
    text = str(exc).lower()
    return "no such table" in text or ("exam_assignees" in text and "does not exist" in text)


def list_assignees(category_id: str) -> list[dict[str, str]]:
    try:
        with common_db.read_connection() as (conn, kind):
            ph = common_db.placeholder(kind)
            rows = conn.execute(
                f"SELECT assignee_type, assignee_key, assigned_by, assigned_at FROM exam_assignees "
                f"WHERE quiz_category_id={ph} ORDER BY assignee_type, assignee_key",
                (category_id,),
            ).fetchall()
    except Exception as exc:
        if _table_missing(exc):
            return []
        raise
    return [
        {
            "type": str(dict(row)["assignee_type"]),
            "key": str(dict(row)["assignee_key"]),
            "assignedBy": str(dict(row).get("assigned_by") or ""),
            "assignedAt": str(dict(row).get("assigned_at") or ""),
        }
        for row in rows
    ]


def assignees_by_category(category_ids: Iterable[str]) -> dict[str, list[dict[str, str]]]:
    wanted = {str(value) for value in category_ids if value}
    if not wanted:
        return {}
    try:
        with common_db.read_connection() as (conn, _kind):
            rows = conn.execute("SELECT quiz_category_id, assignee_type, assignee_key FROM exam_assignees").fetchall()
    except Exception as exc:
        if _table_missing(exc):
            return {}
        raise
    result: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        data = dict(row)
        category_id = str(data["quiz_category_id"])
        if category_id in wanted:
            result.setdefault(category_id, []).append(
                {"type": str(data["assignee_type"]), "key": str(data["assignee_key"])}
            )
    return result


def replace_assignees(category_id: str, items: Iterable[Mapping[str, Any]], actor: Mapping[str, Any]) -> list[dict[str, str]]:
    pairs: list[tuple[str, str]] = []
    for item in items:
        pair = _norm(item)
        if pair not in pairs:
            pairs.append(pair)
    if ("all", "") in pairs:
        pairs = [("all", "")]
    for kind, key in pairs:
        if kind == "user":
            from teacher_app.learning import assignment_service

            if not assignment_service._active_account(key):
                raise ApiError("ASSIGNEE_NOT_FOUND", f"找不到可指派的使用者帳號：{key}", 400)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    by = str(actor.get("username") or "")[:100]
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        conn.execute(f"DELETE FROM exam_assignees WHERE quiz_category_id={ph}", (category_id,))
        for a_type, a_key in pairs:
            conn.execute(
                f"INSERT INTO exam_assignees(quiz_category_id,assignee_type,assignee_key,assigned_by,assigned_at) "
                f"VALUES ({','.join([ph] * 5)})",
                (category_id, a_type, a_key, by, now),
            )
    return list_assignees(category_id)


def _username(user: Mapping[str, Any]) -> str:
    return str(user.get("username") or "").strip().lower()


def _group(user: Mapping[str, Any]) -> str:
    return str(user.get("preferredGroup") or user.get("preferred_group") or user.get("group") or "").strip()


def matches(user: Mapping[str, Any] | None, rows: list[Mapping[str, Any]]) -> bool:
    if not rows:
        return True  # 沒有指派名單＝維持原本行為
    if not user:
        return False
    for row in rows:
        kind, key = str(row.get("type")), str(row.get("key") or "")
        if kind == "all":
            return True
        if kind == "user" and key.lower() == _username(user):
            return True
        if kind == "group" and key and key == _group(user):
            return True
    return False


def _is_manager(user: Mapping[str, Any] | None) -> bool:
    return bool(user) and has_permission(user, "exam.manage")


def filter_for_user(user: Mapping[str, Any] | None, categories: list[dict]) -> list[dict]:
    if _is_manager(user):
        return list(categories)
    table = assignees_by_category(str(item.get("id") or "") for item in categories)
    return [item for item in categories if matches(user, table.get(str(item.get("id") or ""), []))]


def assert_can_take(user: Mapping[str, Any] | None, category_id: str) -> None:
    if _is_manager(user):
        return
    if not matches(user, list_assignees(category_id)):
        raise ApiError("EXAM_NOT_ASSIGNED", "這份考卷沒有指派給你。", 403)
