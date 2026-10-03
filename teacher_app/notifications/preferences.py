"""Authenticated per-account email notification preferences.

In-app actionable notifications remain complete.  These preferences only filter
ordinary email delivery. Critical material-processing failures and confirmed
operational incidents/recoveries are always eligible for email and cannot be
disabled by user preference.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Iterable, Mapping

from teacher_app.common import db as common_db
from teacher_app.common.errors import ApiError

LOGGER = logging.getLogger(__name__)

DEFAULTS = {
    "courseDue": True,
    "examDue": True,
    "retraining": True,
    "teacherReview": True,
}
CRITICAL_KINDS = {"material_failure", "worker_offline", "operational_incident", "operational_recovery"}
_KIND_TO_PREF = {
    "course": "courseDue",
    "due": "courseDue",
    "exam": "examDue",
    "retraining": "retraining",
    "review": "teacherReview",
}
_DB_COLUMNS = {
    "courseDue": "email_course_due",
    "examDue": "email_exam_due",
    "retraining": "email_retraining",
    "teacherReview": "email_teacher_review",
}


def _username(user: Mapping[str, Any] | None) -> str:
    username = str((user or {}).get("username") or "").strip()
    if not username:
        raise ApiError("LOGIN_REQUIRED", "請先登入後再設定通知。", status=401, extra={"loginRequired": True})
    return username


def get_preferences(user: Mapping[str, Any] | None) -> dict[str, Any]:
    username = _username(user)
    values = dict(DEFAULTS)
    try:
        with common_db.read_connection() as (conn, kind):
            ph = common_db.placeholder(kind)
            row = conn.execute(
                f"SELECT email_course_due,email_exam_due,email_retraining,email_teacher_review "
                f"FROM notification_email_preferences WHERE username={ph}",
                (username,),
            ).fetchone()
            if row:
                item = dict(row)
                for key, column in _DB_COLUMNS.items():
                    values[key] = bool(item.get(column, True))
    except Exception as exc:
        # Mixed-version recovery: default-on ordinary notifications until the
        # additive migration is applied. Critical notifications remain protected.
        LOGGER.warning(
            "notification preferences read fallback error_type=%s",
            type(exc).__name__,
        )
    return {
        "emailCategories": values,
        "protectedCategories": ["materialFailure", "workerOffline", "operationalIncidents"],
    }


def update_preferences(user: Mapping[str, Any] | None, payload: Mapping[str, Any] | None) -> dict[str, Any]:
    username = _username(user)
    data = dict(payload or {})
    categories = data.get("emailCategories")
    if not isinstance(categories, Mapping):
        raise ApiError("INVALID_NOTIFICATION_PREFERENCES", "Email 通知偏好格式不正確。", status=400)
    unknown = set(categories) - set(DEFAULTS)
    if unknown:
        raise ApiError("INVALID_NOTIFICATION_PREFERENCES", "包含不支援的通知類別。", status=400)
    current = get_preferences(user)["emailCategories"]
    for key, value in categories.items():
        if type(value) is not bool:
            raise ApiError("INVALID_NOTIFICATION_PREFERENCES", "通知類別設定必須是布林值。", status=400)
        current[key] = value
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        columns = ["username", *_DB_COLUMNS.values(), "updated_at"]
        values = [username, *(current[key] for key in DEFAULTS), now]
        updates = ",".join(f"{column}=excluded.{column}" for column in [*_DB_COLUMNS.values(), "updated_at"])
        conn.execute(
            f"INSERT INTO notification_email_preferences({','.join(columns)}) "
            f"VALUES ({','.join([ph] * len(columns))}) "
            f"ON CONFLICT(username) DO UPDATE SET {updates}",
            tuple(values),
        )
    return {
        "emailCategories": current,
        "protectedCategories": ["materialFailure", "workerOffline", "operationalIncidents"],
    }


def filter_email_events(
    rows: Iterable[Mapping[str, Any]],
    user: Mapping[str, Any] | None,
    *,
    general_enabled: bool = True,
) -> list[dict[str, Any]]:
    prefs = get_preferences(user)["emailCategories"]
    output: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        kind = str(row.get("kind") or "")
        if kind in CRITICAL_KINDS:
            output.append(row)
            continue
        if not general_enabled:
            continue
        preference = _KIND_TO_PREF.get(kind)
        if preference and not prefs.get(preference, True):
            continue
        output.append(row)
    return output


__all__ = ["CRITICAL_KINDS", "DEFAULTS", "filter_email_events", "get_preferences", "update_preferences"]
