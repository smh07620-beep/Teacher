"""Scheduled email delivery for canonical actionable notification events."""
from __future__ import annotations

import datetime as dt
import json
import os
import uuid
from typing import Any, Mapping

from teacher_app.auth import repository as auth_repository
from teacher_app.auth.self_service import _send
from teacher_app.common import db as common_db
from teacher_app.notifications import events, preferences

TAIPEI = dt.timezone(dt.timedelta(hours=8))


def _user_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    roles = row.get("roles") or row.get("roles_json") or []
    if isinstance(roles, str):
        try:
            decoded = json.loads(roles)
            roles = decoded if isinstance(decoded, list) else [roles]
        except Exception:
            roles = [roles]
    return {
        "username": row["username"],
        "name": row.get("display_name", ""),
        "empId": row.get("emp_id", ""),
        "role": row.get("role", "student"),
        "roles": roles,
        "preferredArea": row.get("preferred_area", "internal"),
        "preferredGroup": row.get("preferred_group", "grpBio"),
        "permissions": row.get("permissions") or [],
        "pgyLearner": bool(row.get("pgy_learner", False)),
    }


def _claim(username: str, key: str, kind: str) -> bool:
    with common_db.transaction() as (conn, dbkind):
        ph = common_db.placeholder(dbkind)
        try:
            conn.execute(
                f"INSERT INTO email_notification_log(id,username,notification_key,kind,sent_at) VALUES ({','.join([ph] * 5)})",
                (uuid.uuid4().hex, username, key, kind, dt.datetime.now(dt.timezone.utc).isoformat()),
            )
            return True
        except Exception:
            return False


def _release_claim(username: str, key: str) -> None:
    try:
        with common_db.transaction() as (conn, dbkind):
            ph = common_db.placeholder(dbkind)
            conn.execute(
                f"DELETE FROM email_notification_log WHERE username={ph} AND notification_key={ph}",
                (username, key),
            )
    except Exception:
        pass


def _line(event: Mapping[str, Any]) -> str:
    label = str(event.get("badge") or event.get("kind") or "待辦")
    title = str(event.get("title") or "待處理項目")
    due = events._parse_datetime(event.get("dueAt"))
    suffix = f"（截止 {due.astimezone(TAIPEI).strftime('%Y-%m-%d %H:%M')}）" if due else ""
    detail = str(event.get("detail") or "").strip()
    return f"[{label}] {title}{suffix}" + (f" — {detail}" if detail else "")


def run_due_reminders() -> int:
    """Send one digest per eligible user from the same events used in-app."""
    now = dt.datetime.now(dt.timezone.utc)
    days = max(1, int(os.getenv("EMAIL_REMINDER_DAYS", "3") or 3))
    sent = 0
    for row in auth_repository.list_users():
        if not row.get("active") or not row.get("email"):
            continue
        user = _user_from_row(row)
        try:
            candidates = events.email_events(user, now=now, days=days)
            candidates = preferences.filter_email_events(
                candidates,
                user,
                general_enabled=bool(row.get("email_notifications", True)),
            )
        except Exception:
            continue
        claimed = [event for event in candidates if _claim(user["username"], event["key"], event["kind"])]
        if not claimed:
            continue
        name = str(row.get("display_name") or row["username"])
        body = (
            f"您好 {name}：\n\n"
            "以下是教學平台目前需要你注意的事項：\n"
            + "\n".join(_line(event) for event in claimed)
            + "\n\n請登入教學平台查看或處理。"
        )
        try:
            delivered = bool(_send(row["email"], "醫學檢驗教學平台｜需要處理的學習與教學提醒", body))
        except Exception:
            delivered = False
        if delivered:
            sent += 1
        else:
            for event in claimed:
                _release_claim(user["username"], event["key"])
    return sent


__all__ = ["run_due_reminders"]
