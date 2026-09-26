"""Persistence for immutable learner course-completion certificates."""
from __future__ import annotations

import json
from typing import Any, Mapping

from teacher_app.common import db as common_db


def certificate_to_dict(row: Mapping[str, Any] | Any) -> dict[str, Any]:
    data = dict(row)
    raw = data.pop("evidence_json", "{}") or "{}"
    try:
        evidence = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
    except (TypeError, ValueError, json.JSONDecodeError):
        evidence = {}
    data["empId"] = str(data.pop("emp_id", "") or "")
    data["learnerName"] = str(data.pop("learner_name", "") or "")
    data["courseId"] = str(data.pop("course_id", "") or "")
    data["courseTitle"] = str(data.pop("course_title", "") or "")
    data["area"] = str(data.pop("training_area", "") or "")
    data["group"] = str(data.pop("group_key", "") or "")
    data["completionFingerprint"] = str(data.pop("completion_fingerprint", "") or "")
    data["issuedAt"] = str(data.pop("issued_at", "") or "")
    data["evidence"] = evidence if isinstance(evidence, dict) else {}
    return data


def list_for_user(username: str) -> list[dict[str, Any]]:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        rows = conn.execute(
            f"SELECT * FROM course_completion_certificates WHERE LOWER(username)=LOWER({ph}) "
            "ORDER BY issued_at DESC,id DESC",
            (str(username or "").strip(),),
        ).fetchall()
    return [certificate_to_dict(row) for row in rows]


def get_certificate(certificate_id: str) -> dict[str, Any] | None:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT * FROM course_completion_certificates WHERE id={ph}",
            (str(certificate_id or "").strip(),),
        ).fetchone()
    return certificate_to_dict(row) if row else None


def find_for_fingerprint(username: str, course_id: str, fingerprint: str) -> dict[str, Any] | None:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT * FROM course_completion_certificates WHERE LOWER(username)=LOWER({ph}) "
            f"AND course_id={ph} AND completion_fingerprint={ph}",
            (str(username or "").strip(), str(course_id or "").strip(), str(fingerprint or "").strip()),
        ).fetchone()
    return certificate_to_dict(row) if row else None


def list_material_completion_rows(emp_id: str) -> list[dict[str, Any]]:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        rows = conn.execute(
            f"SELECT * FROM material_progress WHERE emp_id={ph} ORDER BY completed_at DESC",
            (str(emp_id or "").strip(),),
        ).fetchall()
    return [dict(row) for row in rows]


def insert_certificate(values: Mapping[str, Any]) -> dict[str, Any]:
    fields = (
        "id", "username", "emp_id", "learner_name", "course_id", "course_title",
        "training_area", "group_key", "completion_fingerprint", "evidence_json", "issued_at",
    )
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        conn.execute(
            f"INSERT INTO course_completion_certificates ({','.join(fields)}) "
            f"VALUES ({','.join(ph for _ in fields)})",
            tuple(values.get(field) for field in fields),
        )
    return get_certificate(str(values.get("id") or "")) or {}


__all__ = [
    "certificate_to_dict",
    "find_for_fingerprint",
    "get_certificate",
    "insert_certificate",
    "list_for_user",
    "list_material_completion_rows",
]
