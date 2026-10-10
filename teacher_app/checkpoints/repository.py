"""Persistence for slide checkpoints and learner answers."""
from __future__ import annotations

import json
from typing import Any, Mapping

from teacher_app.common import db as common_db

COLUMNS = (
    "id", "material_id", "material_version", "group_key", "page_no", "question",
    "options_json", "correct_index", "explanation", "active",
    "created_by", "created_at", "updated_by", "updated_at",
)


def row_to_checkpoint(row: Any) -> dict:
    data = dict(row) if row is not None else {}
    if not data:
        return {}
    try:
        options = json.loads(data.get("options_json") or "[]")
    except Exception:
        options = []
    return {
        "id": data["id"],
        "materialId": data["material_id"],
        "materialVersion": int(data.get("material_version") or 1),
        "group": data.get("group_key") or "",
        "page": int(data.get("page_no") or 1),
        "question": data.get("question") or "",
        "options": options if isinstance(options, list) else [],
        "correctIndex": int(data.get("correct_index") or 0),
        "explanation": data.get("explanation") or "",
        "active": bool(data.get("active")),
        "createdBy": data.get("created_by") or "",
        "updatedAt": data.get("updated_at") or "",
    }


def list_for_material(material_id: str) -> list[dict]:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        rows = conn.execute(
            f"SELECT * FROM slide_checkpoints WHERE material_id={ph} ORDER BY page_no,created_at,id",
            (str(material_id),),
        ).fetchall()
    return [row_to_checkpoint(row) for row in rows]


def get(checkpoint_id: str) -> dict:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT * FROM slide_checkpoints WHERE id={ph}", (str(checkpoint_id),)
        ).fetchone()
    return row_to_checkpoint(row)


def insert(values: Mapping[str, Any]) -> None:
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        conn.execute(
            "INSERT INTO slide_checkpoints(" + ",".join(COLUMNS) + ") VALUES(" + ",".join([ph] * len(COLUMNS)) + ")",
            tuple(values[column] for column in COLUMNS),
        )


def update(checkpoint_id: str, changes: Mapping[str, Any]) -> None:
    if not changes:
        return
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        sets = ",".join(f"{column}={ph}" for column in changes)
        conn.execute(
            f"UPDATE slide_checkpoints SET {sets} WHERE id={ph}",
            tuple(changes.values()) + (str(checkpoint_id),),
        )


def delete(checkpoint_id: str) -> None:
    # Answers are learning records: they are kept (orphaned rows are harmless
    # and stay auditable) -- only the question definition goes away.
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        conn.execute(f"DELETE FROM slide_checkpoints WHERE id={ph}", (str(checkpoint_id),))


def answers_for_user(username: str, material_id: str) -> dict[str, dict]:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        rows = conn.execute(
            f"SELECT checkpoint_id,chosen_index,is_correct,answered_at FROM slide_checkpoint_answers "
            f"WHERE username={ph} AND material_id={ph}",
            (str(username), str(material_id)),
        ).fetchall()
    return {
        str(dict(r)["checkpoint_id"]): {
            "chosenIndex": int(dict(r)["chosen_index"]),
            "isCorrect": bool(dict(r)["is_correct"]),
            "answeredAt": dict(r)["answered_at"],
        }
        for r in rows
    }


def get_answer(checkpoint_id: str, username: str) -> dict:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT chosen_index,is_correct FROM slide_checkpoint_answers WHERE checkpoint_id={ph} AND username={ph}",
            (str(checkpoint_id), str(username)),
        ).fetchone()
    if row is None:
        return {}
    data = dict(row)
    return {"chosenIndex": int(data["chosen_index"]), "isCorrect": bool(data["is_correct"])}


def record_answer(checkpoint_id: str, username: str, material_id: str, chosen: int, correct: bool, answered_at: str) -> bool:
    """Insert the learner's first answer.  Returns False if one already exists."""
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        exists = conn.execute(
            f"SELECT 1 FROM slide_checkpoint_answers WHERE checkpoint_id={ph} AND username={ph}",
            (str(checkpoint_id), str(username)),
        ).fetchone()
        if exists is not None:
            return False
        conn.execute(
            "INSERT INTO slide_checkpoint_answers(checkpoint_id,username,material_id,chosen_index,is_correct,answered_at) "
            f"VALUES({ph},{ph},{ph},{ph},{ph},{ph})",
            (str(checkpoint_id), str(username), str(material_id), int(chosen), 1 if correct else 0, answered_at),
        )
    return True


def answer_stats(material_id: str) -> dict[str, dict]:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        rows = conn.execute(
            f"SELECT checkpoint_id,COUNT(*) AS n,SUM(is_correct) AS ok FROM slide_checkpoint_answers "
            f"WHERE material_id={ph} GROUP BY checkpoint_id",
            (str(material_id),),
        ).fetchall()
    stats = {}
    for row in rows:
        data = dict(row)
        stats[str(data["checkpoint_id"])] = {"answered": int(data["n"] or 0), "correct": int(data["ok"] or 0)}
    return stats
