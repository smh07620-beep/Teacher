"""Durable per-user read/unread markers for the aggregated notification center.

Notification content remains owned by its source domains (assignments, exams,
PGY and announcements). This module stores only a stable notification key and
the time the authenticated user marked it read.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any, Iterable, Mapping

from teacher_app.common import db as common_db
from teacher_app.common.errors import ApiError


MAX_KEYS = 50
MAX_KEY_LENGTH = 255
_KEY_RE = re.compile(r"^[A-Za-z0-9._~:%+|,@-]+$")


def _username(user: Mapping[str, Any] | None) -> str:
    username = str((user or {}).get("username") or "").strip().lower()
    if not username:
        raise ApiError(
            "LOGIN_REQUIRED",
            "請先登入後再使用通知中心。",
            status=401,
            extra={"loginRequired": True},
        )
    return username[:64]


def normalize_keys(values: Iterable[Any] | None) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        key = str(value or "").strip()
        if not key:
            continue
        if len(key) > MAX_KEY_LENGTH or not _KEY_RE.fullmatch(key):
            raise ApiError("INVALID_NOTIFICATION_KEY", "通知識別碼格式不正確。", status=400)
        if key in seen:
            continue
        seen.add(key)
        keys.append(key)
        if len(keys) > MAX_KEYS:
            raise ApiError(
                "TOO_MANY_NOTIFICATION_KEYS",
                f"一次最多處理 {MAX_KEYS} 筆通知。",
                status=400,
            )
    return keys


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def list_states(user: Mapping[str, Any] | None, keys: Iterable[Any] | None) -> dict[str, dict[str, str]]:
    username = _username(user)
    normalized = normalize_keys(keys)
    if not normalized:
        return {}
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        marks = ",".join([ph] * len(normalized))
        rows = conn.execute(
            f"SELECT notification_key,read_at,updated_at FROM notification_read_state "
            f"WHERE username={ph} AND notification_key IN ({marks})",
            tuple([username] + normalized),
        ).fetchall()
    return {
        str(dict(row).get("notification_key") or ""): {
            "readAt": str(dict(row).get("read_at") or ""),
            "updatedAt": str(dict(row).get("updated_at") or ""),
        }
        for row in rows
        if dict(row).get("notification_key")
    }


def set_read_state(
    user: Mapping[str, Any] | None,
    keys: Iterable[Any] | None,
    *,
    read: bool,
) -> dict[str, dict[str, str]]:
    username = _username(user)
    normalized = normalize_keys(keys)
    if not normalized:
        return {}
    now = _utc_now_iso()
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        if read:
            for key in normalized:
                if kind == "postgres":
                    conn.execute(
                        "INSERT INTO notification_read_state "
                        "(username,notification_key,read_at,updated_at) VALUES (%s,%s,%s,%s) "
                        "ON CONFLICT(username,notification_key) DO UPDATE SET "
                        "read_at=EXCLUDED.read_at,updated_at=EXCLUDED.updated_at",
                        (username, key, now, now),
                    )
                else:
                    conn.execute(
                        "INSERT INTO notification_read_state "
                        "(username,notification_key,read_at,updated_at) VALUES (?,?,?,?) "
                        "ON CONFLICT(username,notification_key) DO UPDATE SET "
                        "read_at=excluded.read_at,updated_at=excluded.updated_at",
                        (username, key, now, now),
                    )
        else:
            marks = ",".join([ph] * len(normalized))
            conn.execute(
                f"DELETE FROM notification_read_state WHERE username={ph} "
                f"AND notification_key IN ({marks})",
                tuple([username] + normalized),
            )
    return list_states(user, normalized)


__all__ = ["MAX_KEYS", "list_states", "normalize_keys", "set_read_state"]
