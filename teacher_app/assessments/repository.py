"""Canonical assessment/category and Question Bank data access."""
from __future__ import annotations

from typing import Any, Mapping

from teacher_app.common import db as common_db
from teacher_app.common import scope


def get_category(category_id: str) -> dict | None:
    if not category_id:
        return None
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT id,title,group_key,training_area,active FROM quiz_categories WHERE id={ph}",
            (category_id,),
        ).fetchone()
    if not row:
        return None
    data = dict(row)
    return {
        "id": str(data.get("id") or ""),
        "title": str(data.get("title") or ""),
        "group": scope.normalize_group(data.get("group_key")),
        "area": scope.normalize_area(data.get("training_area")),
        "active": bool(data.get("active", True)),
    }


def category_labels() -> dict[str, str]:
    with common_db.read_connection() as (conn, _kind):
        rows = conn.execute("SELECT id,title FROM quiz_categories").fetchall()
    return {
        str(dict(row).get("id") or ""): str(dict(row).get("title") or "")
        for row in rows
        if dict(row).get("id")
    }


def list_bank_questions(*, category_id: str = "", status: str = "") -> list[dict]:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        sql = "SELECT * FROM quiz_questions"
        clauses: list[str] = []
        args: list[Any] = []
        if category_id:
            clauses.append(f"quiz_category_id={ph}")
            args.append(category_id)
        if status:
            clauses.append(f"status={ph}")
            args.append(status)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY updated_at DESC, sort_order ASC"
        rows = conn.execute(sql, args).fetchall()
    return [dict(row) for row in rows]


def get_bank_question(question_id: str) -> dict | None:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT * FROM quiz_questions WHERE id={ph}",
            (question_id,),
        ).fetchone()
    return dict(row) if row else None


def list_duplicate_candidates() -> list[dict]:
    with common_db.read_connection() as (conn, _kind):
        rows = conn.execute(
            "SELECT id,question,normalized_hash FROM quiz_questions"
        ).fetchall()
    return [dict(row) for row in rows]


def insert_bank_question(values: Mapping[str, Any]) -> None:
    columns = (
        "id", "quiz_category_id", "tag", "question", "question_type", "options",
        "correct", "explanation", "domain", "topic", "subtopic", "learning_objective",
        "difficulty", "cognitive_level", "tags", "source_material_id", "review_source",
        "status", "origin", "updated_at", "normalized_hash",
    )
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        conn.execute(
            f"INSERT INTO quiz_questions({','.join(columns)}) VALUES({','.join([ph] * len(columns))})",
            tuple(values.get(column) for column in columns),
        )


def update_bank_question(question_id: str, values: Mapping[str, Any]) -> dict | None:
    columns = (
        "question", "options", "correct", "explanation", "topic", "subtopic",
        "learning_objective", "difficulty", "cognitive_level", "tags",
        "source_material_id", "review_source", "status", "origin", "updated_at",
    )
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        conn.execute(
            "UPDATE quiz_questions SET "
            + ",".join(f"{column}={ph}" for column in columns)
            + f",version=version+1 WHERE id={ph}",
            tuple(values.get(column) for column in columns) + (question_id,),
        )
        row = conn.execute(
            f"SELECT * FROM quiz_questions WHERE id={ph}",
            (question_id,),
        ).fetchone()
    return dict(row) if row else None


def delete_bank_question(question_id: str) -> bool:
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        cursor = conn.execute(
            f"DELETE FROM quiz_questions WHERE id={ph}",
            (question_id,),
        )
        return bool(getattr(cursor, "rowcount", 0))


def review_bank_question(
    question_id: str,
    *,
    decision: str,
    username: str,
    stamp: str,
) -> bool:
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        if decision == "accept":
            cursor = conn.execute(
                f"UPDATE quiz_questions SET status={ph},reviewed_by={ph},reviewed_at={ph},updated_at={ph},version=version+1 WHERE id={ph} AND status='draft'",
                ("reviewed", username, stamp, stamp, question_id),
            )
        elif decision == "return":
            cursor = conn.execute(
                f"UPDATE quiz_questions SET status={ph},updated_at={ph},version=version+1 WHERE id={ph}",
                ("draft", stamp, question_id),
            )
        else:
            cursor = conn.execute(
                f"UPDATE quiz_questions SET status={ph},updated_at={ph},version=version+1 WHERE id={ph}",
                ("retired", stamp, question_id),
            )
        return bool(getattr(cursor, "rowcount", 0))


def insert_blueprint(values: Mapping[str, Any]) -> None:
    columns = (
        "id", "quiz_category_id", "question_count", "quotas", "exclude_recent",
        "created_by", "created_at",
    )
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        conn.execute(
            f"INSERT INTO exam_blueprints({','.join(columns)}) VALUES({','.join([ph] * len(columns))})",
            tuple(values.get(column) for column in columns),
        )


def get_blueprint(blueprint_id: str) -> dict | None:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT * FROM exam_blueprints WHERE id={ph}",
            (blueprint_id,),
        ).fetchone()
    return dict(row) if row else None


def get_blueprint_snapshot(blueprint_id: str) -> dict | None:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT id,blueprint_id,quiz_category_id,questions,created_at FROM exam_blueprint_snapshots WHERE blueprint_id={ph}",
            (blueprint_id,),
        ).fetchone()
    return dict(row) if row else None


def list_blueprint_questions(category_id: str) -> list[dict]:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        active = "TRUE" if kind == "postgres" else "1"
        rows = conn.execute(
            f"SELECT * FROM quiz_questions WHERE quiz_category_id={ph} AND status IN ('reviewed','published') AND active={active}",
            (category_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_recent_blueprint_snapshots(category_id: str, limit: int) -> list[dict]:
    if limit <= 0:
        return []
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        rows = conn.execute(
            f"SELECT questions FROM exam_blueprint_snapshots WHERE quiz_category_id={ph} ORDER BY created_at DESC LIMIT {ph}",
            (category_id, int(limit)),
        ).fetchall()
    return [dict(row) for row in rows]


def insert_blueprint_snapshot(values: Mapping[str, Any]) -> None:
    columns = ("id", "blueprint_id", "quiz_category_id", "questions", "created_at")
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        conn.execute(
            f"INSERT INTO exam_blueprint_snapshots({','.join(columns)}) VALUES({','.join([ph] * len(columns))})",
            tuple(values.get(column) for column in columns),
        )


def list_question_attempt_analytics(question_id: str) -> list[dict]:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        rows = conn.execute(
            f"SELECT selected_option,is_correct FROM question_attempt_analytics WHERE question_id={ph}",
            (question_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_bank_question_correct(question_id: str) -> Any:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT correct FROM quiz_questions WHERE id={ph}",
            (question_id,),
        ).fetchone()
    return dict(row).get("correct") if row else None
