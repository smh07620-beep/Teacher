"""PGY SQL repository. No Flask, no HTTP status codes."""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional, Sequence

from teacher_app.common.auth import normalize_role
from teacher_app.common.db import execute, fetch_all, fetch_one, placeholder
from teacher_app.pgy.workflow import normalize_group, utcnow

ASSIGNMENT_COLUMNS = """
        SELECT a.*,
               l.display_name AS learner_name, l.emp_id AS learner_emp_id,
               t.display_name AS teacher_name, t.emp_id AS teacher_emp_id
        FROM pgy_assignments a
        LEFT JOIN user_accounts l ON l.username=a.learner_username
        LEFT JOIN user_accounts t ON t.username=a.teacher_username
"""


class TransitionConflict(Exception):
    """Raised when a conditional status UPDATE matches zero rows."""


def json_load(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return default


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def assignment_dict(row) -> dict[str, Any]:
    d = dict(row)
    return {
        "id": str(d.get("id", "")),
        "learnerUsername": str(d.get("learner_username", "")),
        "learnerName": str(d.get("learner_name", "")),
        "learnerEmpId": str(d.get("learner_emp_id", "")),
        "teacherUsername": str(d.get("teacher_username", "")),
        "teacherName": str(d.get("teacher_name", "")),
        "teacherEmpId": str(d.get("teacher_emp_id", "")),
        "area": str(d.get("training_area", "pgy")),
        "group": str(d.get("group_key", "grpBio")),
        "courseId": str(d.get("course_id", "")),
        "title": str(d.get("title", "")),
        "instructions": str(d.get("instructions", "")),
        "dueAt": str(d.get("due_at", "")),
        "status": str(d.get("status", "assigned")),
        "evidence": json_load(d.get("evidence"), {}),
        "reflection": str(d.get("reflection", "")),
        "studentSubmittedAt": str(d.get("student_submitted_at", "")),
        "teacherSignature": json_load(d.get("teacher_signature"), {}),
        "groupSignature": json_load(d.get("group_signature"), {}),
        "finalConfirmation": json_load(d.get("final_confirmation"), {}),
        "createdBy": str(d.get("created_by", "")),
        "createdAt": str(d.get("created_at", "")),
        "updatedAt": str(d.get("updated_at", "")),
    }


def audit_dict(row) -> dict[str, Any]:
    d = dict(row)
    return {
        "id": d.get("id", ""),
        "assignmentId": d.get("assignment_id", ""),
        "title": d.get("title", ""),
        "group": d.get("group_key", ""),
        "learnerUsername": d.get("learner_username", ""),
        "teacherUsername": d.get("teacher_username", ""),
        "action": d.get("action", ""),
        "fromStatus": d.get("from_status", ""),
        "toStatus": d.get("to_status", ""),
        "actorUsername": d.get("actor_username", ""),
        "actorRole": d.get("actor_role", ""),
        "detail": json_load(d.get("detail"), {}),
        "createdAt": d.get("created_at", ""),
    }


def init_schema(conn, kind: str) -> None:
    execute(
        conn,
        """
            CREATE TABLE IF NOT EXISTS pgy_assignments (
                id TEXT PRIMARY KEY,
                learner_username TEXT NOT NULL,
                teacher_username TEXT NOT NULL,
                training_area TEXT NOT NULL DEFAULT 'pgy',
                group_key TEXT NOT NULL DEFAULT 'grpBio',
                course_id TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                instructions TEXT NOT NULL DEFAULT '',
                due_at TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'assigned',
                evidence TEXT NOT NULL DEFAULT '{}',
                reflection TEXT NOT NULL DEFAULT '',
                student_submitted_at TEXT NOT NULL DEFAULT '',
                teacher_signature TEXT NOT NULL DEFAULT '{}',
                group_signature TEXT NOT NULL DEFAULT '{}',
                final_confirmation TEXT NOT NULL DEFAULT '{}',
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """,
    )
    execute(conn, "CREATE INDEX IF NOT EXISTS idx_pgy_assignments_learner ON pgy_assignments(learner_username, status, updated_at)")
    execute(conn, "CREATE INDEX IF NOT EXISTS idx_pgy_assignments_teacher ON pgy_assignments(teacher_username, status, updated_at)")
    execute(conn, "CREATE INDEX IF NOT EXISTS idx_pgy_assignments_group ON pgy_assignments(group_key, status, updated_at)")
    execute(
        conn,
        """
            CREATE TABLE IF NOT EXISTS pgy_assignment_audit (
                id TEXT PRIMARY KEY,
                assignment_id TEXT NOT NULL,
                action TEXT NOT NULL,
                from_status TEXT NOT NULL DEFAULT '',
                to_status TEXT NOT NULL DEFAULT '',
                actor_username TEXT NOT NULL,
                actor_role TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )
        """,
    )
    execute(conn, "CREATE INDEX IF NOT EXISTS idx_pgy_assignment_audit_assignment ON pgy_assignment_audit(assignment_id, created_at)")
    execute(conn, "CREATE INDEX IF NOT EXISTS idx_pgy_assignment_audit_actor ON pgy_assignment_audit(actor_username, created_at)")
    active_type = "BOOLEAN" if kind == "postgres" else "INTEGER"
    active_default = "TRUE" if kind == "postgres" else "1"
    execute(
        conn,
        f"""
            CREATE TABLE IF NOT EXISTS user_accounts (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL DEFAULT '',
                display_name TEXT NOT NULL,
                emp_id TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL DEFAULT 'student',
                preferred_area TEXT NOT NULL DEFAULT 'internal',
                preferred_group TEXT NOT NULL DEFAULT 'grpBio',
                active {active_type} NOT NULL DEFAULT {active_default},
                session_version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT '',
                last_login_at TEXT NOT NULL DEFAULT ''
            )
        """,
    )
    execute(
        conn,
        """
            CREATE TABLE IF NOT EXISTS courses (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                training_area TEXT NOT NULL DEFAULT 'pgy',
                group_key TEXT NOT NULL DEFAULT 'grpBio'
            )
        """,
    )


def find_user(conn, kind: str, username: str) -> Optional[dict]:
    ph = placeholder(kind)
    return fetch_one(conn, f"SELECT * FROM user_accounts WHERE username={ph}", (username,))


def find_course(conn, kind: str, course_id: str) -> Optional[dict]:
    if not course_id:
        return None
    ph = placeholder(kind)
    try:
        return fetch_one(conn, f"SELECT * FROM courses WHERE id={ph}", (course_id,))
    except Exception:
        return None


def find_active_assignment_for_course(conn, kind: str, learner_username: str, course_id: str) -> Optional[dict]:
    ph = placeholder(kind)
    return fetch_one(
        conn,
        f"SELECT id FROM pgy_assignments WHERE learner_username={ph} AND course_id={ph} AND status NOT IN ('finalized','cancelled') LIMIT 1",
        (learner_username, course_id),
    )


def get_assignment(conn, kind: str, assignment_id: str) -> Optional[dict]:
    ph = placeholder(kind)
    return fetch_one(conn, ASSIGNMENT_COLUMNS + f" WHERE a.id={ph}", (assignment_id,))


def list_assignments(conn, kind: str, where_sql: str, params: Sequence[Any] = ()) -> list[dict]:
    return fetch_all(conn, ASSIGNMENT_COLUMNS + " WHERE " + where_sql + " ORDER BY a.updated_at DESC", tuple(params))


def create_assignment(
    conn,
    kind: str,
    *,
    assignment_id: str,
    learner_username: str,
    teacher_username: str,
    group_key: str,
    course_id: str,
    title: str,
    instructions: str,
    due_at: str,
    created_by: str,
    created_at: str,
) -> None:
    ph = placeholder(kind)
    execute(
        conn,
        f"INSERT INTO pgy_assignments (id,learner_username,teacher_username,training_area,group_key,course_id,title,instructions,due_at,status,evidence,reflection,student_submitted_at,teacher_signature,group_signature,final_confirmation,created_by,created_at,updated_at) VALUES ({','.join([ph] * 19)})",
        (
            assignment_id,
            learner_username,
            teacher_username,
            "pgy",
            group_key,
            course_id,
            title,
            instructions,
            due_at,
            "assigned",
            "{}",
            "",
            "",
            "{}",
            "{}",
            "{}",
            created_by,
            created_at,
            created_at,
        ),
    )


def update_assignment_draft(conn, kind: str, assignment_id: str, fields: dict[str, Any]) -> None:
    if not fields:
        return
    ph = placeholder(kind)
    assignments = []
    values: list[Any] = []
    for column, value in fields.items():
        assignments.append(f"{column}={ph}")
        values.append(value)
    values.append(assignment_id)
    execute(conn, f"UPDATE pgy_assignments SET {','.join(assignments)} WHERE id={ph}", tuple(values))


def transition_status(
    conn,
    kind: str,
    assignment_id: str,
    expected_status: str,
    new_status: str,
    extra: Optional[dict[str, Any]] = None,
) -> None:
    ph = placeholder(kind)
    extra = extra or {}
    columns = [f"status={ph}"]
    values: list[Any] = [new_status]
    for column, value in extra.items():
        columns.append(f"{column}={ph}")
        values.append(value)
    values.extend([assignment_id, expected_status])
    cursor = execute(
        conn,
        f"UPDATE pgy_assignments SET {','.join(columns)} WHERE id={ph} AND status={ph}",
        tuple(values),
    )
    if getattr(cursor, "rowcount", 1) != 1:
        raise TransitionConflict("此指派狀態已由其他請求更新，請重新整理後再操作。")


def write_audit(
    conn,
    kind: str,
    *,
    assignment_id: str,
    action: str,
    from_status: str,
    to_status: str,
    actor_username: str,
    actor_role: str,
    detail: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    ph = placeholder(kind)
    event = {
        "id": uuid.uuid4().hex,
        "assignment_id": assignment_id,
        "action": action,
        "from_status": from_status or "",
        "to_status": to_status or "",
        "actor_username": actor_username,
        "actor_role": actor_role,
        "detail": detail or {},
        "created_at": utcnow(),
    }
    execute(
        conn,
        f"INSERT INTO pgy_assignment_audit (id,assignment_id,action,from_status,to_status,actor_username,actor_role,detail,created_at) VALUES ({','.join([ph] * 9)})",
        (
            event["id"],
            event["assignment_id"],
            event["action"],
            event["from_status"],
            event["to_status"],
            event["actor_username"],
            event["actor_role"],
            json_dump(event["detail"]),
            event["created_at"],
        ),
    )
    return event


def list_audit(conn, kind: str, *, assignment_id: str = "", group_key: str = "") -> list[dict]:
    ph = placeholder(kind)
    where, params = [], []
    if assignment_id:
        where.append(f"x.assignment_id={ph}")
        params.append(assignment_id)
    if group_key:
        where.append(f"a.group_key={ph}")
        params.append(group_key)
    sql = """
                SELECT x.*, a.group_key, a.learner_username, a.teacher_username, a.title
                FROM pgy_assignment_audit x
                LEFT JOIN pgy_assignments a ON a.id=x.assignment_id
            """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY x.created_at DESC"
    return fetch_all(conn, sql, tuple(params))


def find_assignment_candidates(conn, kind: str, group_key: str) -> tuple[list[dict], list[dict]]:
    rows = fetch_all(
        conn,
        "SELECT username,display_name,emp_id,role,preferred_group,active FROM user_accounts ORDER BY display_name ASC",
    )
    students, teachers = [], []
    for d in rows:
        if not bool(d.get("active", True)):
            continue
        role = normalize_role(d.get("role"))
        group = normalize_group(d.get("preferred_group"))
        if group != group_key:
            continue
        item = {
            "username": d.get("username", ""),
            "name": d.get("display_name", ""),
            "empId": d.get("emp_id", ""),
            "group": group,
        }
        if role == "student":
            students.append(item)
        elif role == "clinical_teacher":
            teachers.append(item)
    return students, teachers
