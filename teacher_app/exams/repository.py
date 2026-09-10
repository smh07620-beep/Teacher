"""Persistence for exam attempts and their resulting exam records."""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterator, Mapping


class AttemptConflict(RuntimeError):
    pass


def placeholder(kind: str) -> str:
    return "%s" if kind == "postgres" else "?"


def json_load(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return default


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


@contextmanager
def transaction(base) -> Iterator[tuple[Any, str]]:
    conn, kind = base._db_conn()
    try:
        if kind == "postgres":
            with conn.transaction():
                yield conn, kind
            return
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn, kind
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()
    finally:
        conn.close()


def init_schema(base) -> None:
    conn, _kind = base._db_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS exam_attempts (
                id TEXT PRIMARY KEY, username TEXT NOT NULL, emp_id TEXT NOT NULL DEFAULT '',
                quiz_category_id TEXT NOT NULL, quiz_title TEXT NOT NULL DEFAULT '',
                group_key TEXT NOT NULL DEFAULT 'grpBio', training_area TEXT NOT NULL DEFAULT 'internal',
                course_id TEXT NOT NULL DEFAULT '', passing_score INTEGER NOT NULL DEFAULT 80,
                publication_id TEXT NOT NULL DEFAULT '', publication_hash TEXT NOT NULL DEFAULT '',
                questions_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'started',
                record_id TEXT NOT NULL DEFAULT '', started_at TEXT NOT NULL, submitted_at TEXT NOT NULL DEFAULT ''
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_exam_attempts_user ON exam_attempts(username, status, started_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_exam_attempts_category ON exam_attempts(quiz_category_id, status, started_at)")
    finally:
        conn.close()


def get_attempt(conn, kind: str, attempt_id: str) -> dict[str, Any] | None:
    row = conn.execute(f"SELECT * FROM exam_attempts WHERE id={placeholder(kind)}", (attempt_id,)).fetchone()
    return dict(row) if row else None


def create_attempt(conn, kind: str, attempt: Mapping[str, Any]) -> None:
    ph = placeholder(kind)
    columns = ("id", "username", "emp_id", "quiz_category_id", "quiz_title", "group_key", "training_area",
               "course_id", "passing_score", "publication_id", "publication_hash", "questions_json", "status",
               "record_id", "started_at", "submitted_at")
    conn.execute(f"INSERT INTO exam_attempts ({','.join(columns)}) VALUES ({','.join([ph] * len(columns))})",
                 tuple(attempt[column] for column in columns))


def mark_submitted(conn, kind: str, attempt_id: str, record_id: str, submitted_at: str) -> None:
    ph = placeholder(kind)
    cursor = conn.execute(
        f"UPDATE exam_attempts SET status={ph},record_id={ph},submitted_at={ph} WHERE id={ph} AND status={ph}",
        ("submitted", record_id, submitted_at, attempt_id, "started"),
    )
    if getattr(cursor, "rowcount", 0) != 1:
        raise AttemptConflict("考核狀態已由其他請求更新，請重新整理。")


def insert_exam_record(conn, kind: str, *, record_id: str, user: Mapping[str, Any], attempt: Mapping[str, Any],
                       answers_detail: list[dict[str, Any]], score: int, status: str, correct_count: int,
                       wrong_count: int, evaluator_name: str, evaluator_title: str, examinee_role: str,
                       submitted_at: str) -> None:
    ph = placeholder(kind)
    review_status = "pending" if any(item.get("questionType") == "essay" for item in answers_detail) else "completed"
    values = (
        record_id, submitted_at, str(user.get("name") or "")[:100],
        str(user.get("empId") or user.get("emp_id") or "")[:100], str(examinee_role)[:100], evaluator_name,
        evaluator_title, str(attempt.get("quiz_title") or "")[:255], int(score), str(status)[:30],
        int(correct_count), int(wrong_count), json_dump(answers_detail), str(attempt.get("group_key") or "")[:100],
        str(attempt.get("training_area") or "")[:30], str(attempt.get("course_id") or "")[:100], review_status,
        str(attempt.get("quiz_category_id") or "")[:100], int(attempt.get("passing_score", 80) or 80),
        str(attempt.get("publication_id") or "")[:100], str(attempt.get("publication_hash") or "")[:64],
    )
    conn.execute(f"""INSERT INTO exam_records
        (id,created_at,name,emp_id,role,evaluator_name,evaluator_title,quiz_title,score,status,correct_count,
         wrong_count,answers_detail,group_key,training_area,course_id,review_status,quiz_category_id,
         passing_score,publication_id,publication_hash) VALUES ({','.join([ph] * 21)})""", values)
