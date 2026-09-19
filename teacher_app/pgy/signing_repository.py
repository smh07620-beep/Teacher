"""Canonical PGY signing read helpers.

No Flask/request objects and no legacy application host dependency.
"""
from __future__ import annotations

from teacher_app.common.auth import user_roles
from teacher_app.common.db import fetch_all, fetch_one, placeholder
from teacher_app.common.scope import normalize_group


def list_candidates(conn, kind: str, group_key: str) -> tuple[list[dict], list[dict]]:
    """Return active learner/clinical-teacher candidates, multi-role aware."""
    rows = fetch_all(
        conn,
        "SELECT username,display_name,emp_id,role,roles_json,preferred_group,active "
        "FROM user_accounts ORDER BY display_name ASC",
    )
    students: list[dict] = []
    teachers: list[dict] = []
    for row in rows:
        data = dict(row)
        if not bool(data.get("active", True)):
            continue
        group = normalize_group(data.get("preferred_group"))
        if group != group_key:
            continue
        roles = user_roles({
            "role": data.get("role", "student"),
            "roles_json": data.get("roles_json", "[]"),
        })
        item = {
            "username": data.get("username", ""),
            "name": data.get("display_name", ""),
            "empId": data.get("emp_id", ""),
            "group": group,
            "roles": roles,
        }
        if "student" in roles:
            students.append(item)
        if "clinical_teacher" in roles:
            teachers.append(item)
    return students, teachers


def get_sign_mode_row(conn, kind: str, assignment_id: str):
    ph = placeholder(kind)
    return fetch_one(
        conn,
        f"SELECT sign_mode FROM pgy_assignments WHERE id={ph}",
        (assignment_id,),
    )
