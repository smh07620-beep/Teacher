"""Canonical announcement persistence, audience rules, and JSON projection."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Mapping

from teacher_app.common import db as common_db
from teacher_app.common.auth import has_permission
from teacher_app.courses import repository as course_repository
from teacher_app.learning import access as learning_access
from teacher_app.learning import assignment_repository


KINDS = {"teaching", "system"}
SCOPE_TYPES = {"all", "group", "course"}


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off"}
    return bool(value)


def _columns(conn, kind: str) -> set[str]:
    if kind == "postgres":
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema=current_schema() AND table_name='announcements'"
        ).fetchall()
        return {str(dict(row).get("column_name") or row[0]) for row in rows}
    return {str(row[1]) for row in conn.execute("PRAGMA table_info(announcements)").fetchall()}


def _clean(value: Any, limit: int) -> str:
    return str(value or "").replace("\x00", " ").strip()[:limit]


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _normalize_time(value: Any) -> str:
    text = _clean(value, 80)
    if not text:
        return ""
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("公告日期時間格式不正確") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc).isoformat()


def row_to_dict(row: Mapping[str, Any] | Any) -> dict[str, Any]:
    data = dict(row)
    return {
        "id": str(data.get("id", "")),
        "title": str(data.get("title", "")),
        "body": str(data.get("body", "")),
        "active": _bool(data.get("active", True)),
        "createdAt": str(data.get("created_at", "")),
        "publishedAt": str(data.get("published_at", "")),
        "kind": str(data.get("kind") or "system"),
        "scopeType": str(data.get("scope_type") or "all"),
        "area": str(data.get("training_area") or ""),
        "group": str(data.get("group_key") or ""),
        "courseId": str(data.get("course_id") or ""),
        "startsAt": str(data.get("starts_at") or ""),
        "endsAt": str(data.get("ends_at") or ""),
        "pinned": _bool(data.get("pinned", False)),
        "emailEnabled": _bool(data.get("email_enabled", False)),
        "requireRead": _bool(data.get("require_read", False)),
        "createdBy": str(data.get("created_by") or ""),
    }


def _normalize_payload(data: Mapping[str, Any], *, existing: Mapping[str, Any] | None = None) -> dict[str, Any]:
    old = dict(existing or {})
    title = _clean(data.get("title", old.get("title", "")), 200)
    body = _clean(data.get("body", old.get("body", "")), 4000)
    if not title:
        raise ValueError("公告標題不能空白")

    kind = _clean(data.get("kind", old.get("kind", "system")), 20).lower() or "system"
    if kind not in KINDS:
        raise ValueError("公告類型不正確")

    scope_type = _clean(data.get("scopeType", old.get("scopeType", "all")), 20).lower() or "all"
    if scope_type not in SCOPE_TYPES:
        raise ValueError("公告對象範圍不正確")

    area = _clean(data.get("area", old.get("area", "")), 40)
    group = _clean(data.get("group", old.get("group", "")), 80)
    course_id = _clean(data.get("courseId", old.get("courseId", "")), 120)

    if kind == "system":
        scope_type, area, group, course_id = "all", "", "", ""
    elif scope_type == "all":
        area, group, course_id = "", "", ""
    elif scope_type == "group":
        if not group:
            raise ValueError("組別公告必須指定組別")
        course_id = ""
    else:
        if not course_id:
            raise ValueError("課程公告必須指定課程")
        course = course_repository.get_course(course_id)
        if not course:
            raise ValueError("找不到公告指定的課程")
        area = str(course.get("area") or "")
        group = str(course.get("group") or "")
        if not group:
            raise ValueError("無法確認課程公告的組別範圍")

    starts_at = _normalize_time(data.get("startsAt", old.get("startsAt", "")))
    ends_at = _normalize_time(data.get("endsAt", old.get("endsAt", "")))
    if starts_at and ends_at and ends_at <= starts_at:
        raise ValueError("公告截止時間必須晚於開始時間")

    return {
        "title": title,
        "body": body,
        "active": _bool(data.get("active", old.get("active", True))),
        "kind": kind,
        "scopeType": scope_type,
        "area": area,
        "group": group,
        "courseId": course_id,
        "startsAt": starts_at,
        "endsAt": ends_at,
        "pinned": _bool(data.get("pinned", old.get("pinned", False))),
        "emailEnabled": _bool(data.get("emailEnabled", old.get("emailEnabled", False))),
        "requireRead": _bool(data.get("requireRead", old.get("requireRead", False))),
        "createdBy": _clean(data.get("createdBy", old.get("createdBy", "")), 120),
    }


def _within_window(item: Mapping[str, Any], now: dt.datetime) -> bool:
    for key, is_start in (("startsAt", True), ("endsAt", False)):
        raw = str(item.get(key) or "").strip()
        if not raw:
            continue
        try:
            point = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if point.tzinfo is None:
                point = point.replace(tzinfo=dt.timezone.utc)
            point = point.astimezone(dt.timezone.utc)
        except ValueError:
            continue
        if is_start and now < point:
            return False
        if not is_start and now > point:
            return False
    return True


def _course_ids_for_user(user: Mapping[str, Any] | None) -> set[str]:
    if not user:
        return set()
    username = str(user.get("username") or "").strip()
    if not username:
        return set()
    area, group = learning_access.preferred_learning_scope(user)
    return assignment_repository.course_ids(
        assignment_repository.list_for_user(username=username, area=area, group=group)
    )


def _visible_to_user(
    item: Mapping[str, Any],
    user: Mapping[str, Any] | None,
    *,
    assigned_course_ids: set[str],
) -> bool:
    if str(item.get("kind") or "system") == "system":
        return True
    scope_type = str(item.get("scopeType") or "all")
    if scope_type == "all":
        return True
    if not user:
        return False
    if learning_access.has_global_learning_access(user):
        return True

    user_area, user_group = learning_access.preferred_learning_scope(user)
    item_area = str(item.get("area") or "")
    item_group = str(item.get("group") or "")
    if item_area and item_area != user_area:
        return False
    if item_group and item_group != user_group:
        return False
    if scope_type == "group":
        return True
    if scope_type == "course":
        course_id = str(item.get("courseId") or "")
        if not course_id:
            return False
        if has_permission(user, "announcement.manage"):
            course = course_repository.get_course(course_id)
            return bool(course and learning_access.can_access_learning_item(user, course))
        return course_id in assigned_course_ids
    return False


def get(announcement_id: str) -> dict[str, Any] | None:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT * FROM announcements WHERE id={ph}",
            (str(announcement_id or ""),),
        ).fetchone()
    return row_to_dict(row) if row else None


def list_public(limit: int = 8, *, user: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    bounded_limit = max(1, min(50, int(limit)))
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        rows = conn.execute(
            f"SELECT * FROM announcements WHERE active={ph} "
            "ORDER BY published_at DESC, created_at DESC",
            (True if kind == "postgres" else 1,),
        ).fetchall()
    current = _utc_now()
    assigned = _course_ids_for_user(user)
    visible = [
        row_to_dict(row)
        for row in rows
        if _within_window(row_to_dict(row), current)
        and _visible_to_user(row_to_dict(row), user, assigned_course_ids=assigned)
    ]
    visible.sort(
        key=lambda item: (
            1 if item.get("pinned") else 0,
            str(item.get("publishedAt") or item.get("createdAt") or ""),
        ),
        reverse=True,
    )
    return visible[:bounded_limit]


def list_admin(*, kind: str = "", group: str = "") -> list[dict[str, Any]]:
    with common_db.read_connection() as (conn, _kind):
        rows = conn.execute(
            "SELECT * FROM announcements ORDER BY created_at DESC"
        ).fetchall()
    items = [row_to_dict(row) for row in rows]
    if kind:
        items = [item for item in items if item.get("kind") == kind]
    if group:
        items = [
            item for item in items
            if item.get("kind") == "teaching"
            and str(item.get("group") or "") == group
        ]
    return items


def create(data: Mapping[str, Any]) -> dict[str, Any]:
    payload = _normalize_payload(data)
    announcement_id = uuid.uuid4().hex
    now = _utc_now_iso()
    published = now if payload["active"] else ""
    values = {
        "id": announcement_id,
        "title": payload["title"],
        "body": payload["body"],
        "active": payload["active"],
        "created_at": now,
        "published_at": published,
        "kind": payload["kind"],
        "scope_type": payload["scopeType"],
        "training_area": payload["area"],
        "group_key": payload["group"],
        "course_id": payload["courseId"],
        "starts_at": payload["startsAt"],
        "ends_at": payload["endsAt"],
        "pinned": payload["pinned"],
        "email_enabled": payload["emailEnabled"],
        "require_read": payload["requireRead"],
        "created_by": payload["createdBy"],
    }
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        columns = _columns(conn, kind)
        fields = [name for name in values if name in columns]
        stored = []
        for field in fields:
            value = values[field]
            if field in {"active", "pinned", "email_enabled", "require_read"} and kind != "postgres":
                value = int(bool(value))
            stored.append(value)
        conn.execute(
            f"INSERT INTO announcements ({','.join(fields)}) "
            f"VALUES ({','.join(ph for _ in fields)})",
            tuple(stored),
        )
        row = conn.execute(
            f"SELECT * FROM announcements WHERE id={ph}",
            (announcement_id,),
        ).fetchone()
    return row_to_dict(row)


def update(announcement_id: str, data: Mapping[str, Any]) -> dict[str, Any] | None:
    current = get(announcement_id)
    if not current:
        return None
    payload = _normalize_payload(data, existing=current)
    published = current["publishedAt"] or (_utc_now_iso() if payload["active"] else "")
    values = {
        "title": payload["title"],
        "body": payload["body"],
        "active": payload["active"],
        "published_at": published,
        "kind": payload["kind"],
        "scope_type": payload["scopeType"],
        "training_area": payload["area"],
        "group_key": payload["group"],
        "course_id": payload["courseId"],
        "starts_at": payload["startsAt"],
        "ends_at": payload["endsAt"],
        "pinned": payload["pinned"],
        "email_enabled": payload["emailEnabled"],
        "require_read": payload["requireRead"],
        "created_by": payload["createdBy"],
    }
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        columns = _columns(conn, kind)
        fields = [name for name in values if name in columns]
        stored = []
        for field in fields:
            value = values[field]
            if field in {"active", "pinned", "email_enabled", "require_read"} and kind != "postgres":
                value = int(bool(value))
            stored.append(value)
        conn.execute(
            "UPDATE announcements SET "
            + ",".join(f"{field}={ph}" for field in fields)
            + f" WHERE id={ph}",
            tuple(stored + [announcement_id]),
        )
        row = conn.execute(
            f"SELECT * FROM announcements WHERE id={ph}",
            (announcement_id,),
        ).fetchone()
    return row_to_dict(row)


def delete(announcement_id: str) -> bool:
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT id FROM announcements WHERE id={ph}",
            (announcement_id,),
        ).fetchone()
        if not row:
            return False
        conn.execute(
            f"DELETE FROM announcements WHERE id={ph}",
            (announcement_id,),
        )
    return True


__all__ = [
    "KINDS", "SCOPE_TYPES", "create", "delete", "get", "list_admin",
    "list_public", "row_to_dict", "update",
]
