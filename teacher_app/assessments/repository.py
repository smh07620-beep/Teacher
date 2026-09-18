"""Canonical assessment/category and Question Bank data access."""
from __future__ import annotations

import json
from typing import Any, Mapping

from teacher_app.common import db as common_db
from teacher_app.common import scope


def category_row_to_dict(row) -> dict:
    data = dict(row)
    data["desc"] = data.pop("description", "")
    data["dateAdded"] = data.pop("date_added", "")
    data["active"] = bool(data.get("active", True))
    data["blindMode"] = bool(data.pop("blind_mode", False))
    data["group"] = scope.normalize_group(data.pop("group_key", scope.DEFAULT_GROUP))
    data["area"] = scope.normalize_area(data.pop("training_area", scope.DEFAULT_TRAINING_AREA))
    data["courseId"] = data.pop("course_id", "") or ""
    data["sortOrder"] = int(data.pop("sort_order", 0) or 0)
    try:
        data["drawCount"] = max(0, int(data.pop("draw_count", 0) or 0))
    except (TypeError, ValueError):
        data["drawCount"] = 0
    try:
        data["passingScore"] = max(1, min(100, int(data.pop("passing_score", 80) or 80)))
    except (TypeError, ValueError):
        data["passingScore"] = 80
    data["audience"] = str(data.pop("audience", "") or "")
    raw_rules = data.pop("draw_rules", {}) or {}
    if isinstance(raw_rules, str):
        try:
            raw_rules = json.loads(raw_rules)
        except (TypeError, ValueError):
            raw_rules = {}
    data["drawRules"] = raw_rules if isinstance(raw_rules, dict) else {}
    review_status = str(data.pop("review_status", "approved") or "approved").lower()
    data["reviewStatus"] = review_status if review_status in {"draft", "approved"} else "draft"
    data["reviewerName"] = str(data.pop("reviewer_name", "") or "")
    data["reviewedAt"] = str(data.pop("reviewed_at", "") or "")
    data["publishedAt"] = str(data.pop("published_at", "") or "")
    data["publicationId"] = str(data.pop("publication_id", "") or "")
    data["publicationHash"] = str(data.pop("publication_hash", "") or "")
    data["workflowStage"] = "published" if data["active"] else ("reviewed" if data["reviewStatus"] == "approved" else "draft")
    return data


def question_row_to_dict(row) -> dict:
    data = dict(row)
    raw_options = data.pop("options", "[]")
    if isinstance(raw_options, str):
        try:
            raw_options = json.loads(raw_options)
        except (TypeError, ValueError):
            raw_options = []
    data["options"] = raw_options if isinstance(raw_options, list) else []
    raw_config = data.pop("answer_config", {}) or {}
    if isinstance(raw_config, str):
        try:
            raw_config = json.loads(raw_config)
        except (TypeError, ValueError):
            raw_config = {}
    data["answerConfig"] = raw_config if isinstance(raw_config, dict) else {}
    data["questionType"] = data.pop("question_type", "choice")
    difficulty = str(data.pop("difficulty", "standard") or "standard").lower()
    data["difficulty"] = difficulty if difficulty in {"basic", "standard", "advanced"} else "standard"
    data["imageUrl"] = data.pop("image_url", "")
    data["quizCategoryId"] = data.pop("quiz_category_id", "")
    data["sortOrder"] = int(data.pop("sort_order", 0) or 0)
    data["active"] = bool(data.get("active", True))
    return data


def get_category_full(category_id: str) -> dict | None:
    if not category_id:
        return None
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(f"SELECT * FROM quiz_categories WHERE id={ph}", (category_id,)).fetchone()
    return category_row_to_dict(row) if row else None


def get_category(category_id: str) -> dict | None:
    full = get_category_full(category_id)
    if not full:
        return None
    return {
        "id": str(full.get("id") or ""),
        "title": str(full.get("title") or ""),
        "group": full.get("group"),
        "area": full.get("area"),
        "active": bool(full.get("active", True)),
    }


def list_categories(
    group_key: str | None = None,
    training_area: str | None = None,
    include_inactive: bool = False,
) -> list[dict]:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        clauses: list[str] = []
        params: list[Any] = []
        if group_key:
            clauses.append(f"group_key={ph}")
            params.append(scope.normalize_group(group_key))
        if training_area:
            clauses.append(f"training_area={ph}")
            params.append(scope.normalize_area(training_area))
        if not include_inactive:
            clauses.append("active=" + ("TRUE" if kind == "postgres" else "1"))
        sql = "SELECT * FROM quiz_categories"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY sort_order ASC, date_added ASC"
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [category_row_to_dict(row) for row in rows]


def list_categories_with_counts(
    group_key: str | None = None,
    training_area: str | None = None,
    include_inactive: bool = True,
) -> list[dict]:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        clauses: list[str] = []
        params: list[Any] = []
        if group_key:
            clauses.append(f"group_key={ph}")
            params.append(scope.normalize_group(group_key))
        if training_area:
            clauses.append(f"training_area={ph}")
            params.append(scope.normalize_area(training_area))
        if not include_inactive:
            clauses.append("active=" + ("TRUE" if kind == "postgres" else "1"))
        sql = "SELECT * FROM quiz_categories"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY sort_order ASC, date_added ASC"
        categories = [category_row_to_dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]
        ids = [str(item.get("id") or "") for item in categories if item.get("id")]
        counts: dict[str, int] = {}
        if ids:
            placeholders = ",".join([ph] * len(ids))
            count_sql = f"SELECT quiz_category_id,COUNT(*) AS cnt FROM quiz_questions WHERE quiz_category_id IN ({placeholders})"
            count_sql += " AND active=" + ("TRUE" if kind == "postgres" else "1")
            count_sql += " GROUP BY quiz_category_id"
            for row in conn.execute(count_sql, tuple(ids)).fetchall():
                mapped = dict(row)
                counts[str(mapped.get("quiz_category_id") or "")] = int(mapped.get("cnt", 0) or 0)
    for category in categories:
        category["questionCount"] = counts.get(str(category.get("id") or ""), 0)
    return categories


def list_questions(category_id: str, include_inactive: bool = False) -> list[dict]:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        sql = f"SELECT * FROM quiz_questions WHERE quiz_category_id={ph}"
        if not include_inactive:
            sql += " AND active=" + ("TRUE" if kind == "postgres" else "1")
        sql += " ORDER BY sort_order ASC"
        rows = conn.execute(sql, (category_id,)).fetchall()
    return [question_row_to_dict(row) for row in rows]


def get_question(question_id: str) -> dict | None:
    if not question_id:
        return None
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(f"SELECT * FROM quiz_questions WHERE id={ph}", (question_id,)).fetchone()
    return question_row_to_dict(row) if row else None


def question_counts(category_ids: list[str], include_inactive: bool = False) -> dict[str, int]:
    ids = [str(value) for value in category_ids if value]
    if not ids:
        return {}
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        placeholders = ",".join([ph] * len(ids))
        sql = f"SELECT quiz_category_id,COUNT(*) AS cnt FROM quiz_questions WHERE quiz_category_id IN ({placeholders})"
        if not include_inactive:
            sql += " AND active=" + ("TRUE" if kind == "postgres" else "1")
        sql += " GROUP BY quiz_category_id"
        rows = conn.execute(sql, tuple(ids)).fetchall()
    return {
        str(dict(row).get("quiz_category_id") or ""): int(dict(row).get("cnt", 0) or 0)
        for row in rows
    }


def create_category(values: Mapping[str, Any]) -> dict | None:
    with common_db.transaction() as (conn, kind):
        group = str(values.get("group_key") or scope.DEFAULT_GROUP)
        order = next_category_sort_order_on_connection(conn, kind, group=group)
        data = dict(values)
        data["sort_order"] = order
        insert_category_on_connection(conn, kind, data)
    return get_category_full(str(values.get("id") or ""))


def next_category_sort_order_on_connection(
    conn,
    kind: str,
    *,
    group: str,
    training_area: str | None = None,
) -> int:
    ph = common_db.placeholder(kind)
    sql = f"SELECT COALESCE(MAX(sort_order),-1) AS m FROM quiz_categories WHERE group_key={ph}"
    params: tuple[Any, ...] = (group,)
    if training_area is not None:
        sql += f" AND training_area={ph}"
        params = (group, training_area)
    row = conn.execute(sql, params).fetchone()
    current = dict(row).get("m", -1) if row is not None else -1
    return int(current if current is not None else -1) + 1


def insert_category_on_connection(conn, kind: str, values: Mapping[str, Any]) -> None:
    ph = common_db.placeholder(kind)
    columns = (
        "id", "group_key", "training_area", "course_id", "title", "description",
        "sort_order", "date_added", "active", "draw_count", "passing_score",
        "audience", "draw_rules", "review_status", "reviewer_name", "reviewed_at",
        "published_at",
    )
    data = dict(values)
    data["active"] = bool(data.get("active", False)) if kind == "postgres" else int(bool(data.get("active", False)))
    placeholders = [ph] * len(columns)
    if kind == "postgres":
        placeholders[12] = f"{ph}::jsonb"
    conn.execute(
        f"INSERT INTO quiz_categories ({','.join(columns)}) VALUES ({','.join(placeholders)})",
        tuple(data.get(column) for column in columns),
    )


def update_category(category_id: str, values: Mapping[str, Any], *, reset_publication: bool) -> None:
    fields = (
        "title", "description", "active", "blind_mode", "draw_count", "passing_score",
        "audience", "course_id", "draw_rules", "review_status", "reviewer_name",
        "reviewed_at", "published_at",
    )
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        data = dict(values)
        data["active"] = bool(data.get("active")) if kind == "postgres" else int(bool(data.get("active")))
        data["blind_mode"] = bool(data.get("blind_mode")) if kind == "postgres" else int(bool(data.get("blind_mode")))
        assignments = []
        params: list[Any] = []
        for field in fields:
            assignments.append(f"{field}={ph}::jsonb" if kind == "postgres" and field == "draw_rules" else f"{field}={ph}")
            params.append(data.get(field))
        params.append(category_id)
        conn.execute(
            f"UPDATE quiz_categories SET {','.join(assignments)} WHERE id={ph}",
            tuple(params),
        )
        if reset_publication:
            conn.execute(
                f"UPDATE quiz_categories SET publication_id='',publication_hash='' WHERE id={ph}",
                (category_id,),
            )


def mark_category_reviewed(category_id: str, *, reviewer: str, reviewed_at: str) -> None:
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        conn.execute(
            f"UPDATE quiz_categories SET review_status={ph},reviewer_name={ph},reviewed_at={ph},active={ph} WHERE id={ph}",
            ("approved", reviewer, reviewed_at, False if kind == "postgres" else 0, category_id),
        )


def list_publications(category_id: str, limit: int = 30) -> list[dict]:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        rows = conn.execute(
            f"SELECT id,created_at,reviewer_name,snapshot_hash FROM quiz_publications "
            f"WHERE quiz_category_id={ph} ORDER BY created_at DESC LIMIT {ph}",
            (category_id, max(1, min(200, int(limit)))),
        ).fetchall()
    return [dict(row) for row in rows]


def publish_category(
    category_id: str,
    *,
    publication_id: str,
    created_at: str,
    reviewer_name: str,
    snapshot_hash: str,
    snapshot: Mapping[str, Any],
) -> None:
    payload = json.dumps(snapshot, ensure_ascii=False)
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        snapshot_value = f"{ph}::jsonb" if kind == "postgres" else ph
        conn.execute(
            f"INSERT INTO quiz_publications (id,quiz_category_id,created_at,reviewer_name,snapshot_hash,snapshot) "
            f"VALUES ({ph},{ph},{ph},{ph},{ph},{snapshot_value})",
            (publication_id, category_id, created_at, reviewer_name, snapshot_hash, payload),
        )
        conn.execute(
            f"UPDATE quiz_categories SET active={ph},published_at={ph},publication_id={ph},publication_hash={ph} WHERE id={ph}",
            (True if kind == "postgres" else 1, created_at, publication_id, snapshot_hash, category_id),
        )


def delete_category_on_connection(conn, kind: str, category_id: str) -> None:
    ph = common_db.placeholder(kind)
    conn.execute(f"DELETE FROM quiz_questions WHERE quiz_category_id={ph}", (category_id,))
    conn.execute(f"DELETE FROM quiz_categories WHERE id={ph}", (category_id,))


def clear_course_links_on_connection(conn, kind: str, course_id: str) -> None:
    ph = common_db.placeholder(kind)
    conn.execute(f"UPDATE quiz_categories SET course_id='' WHERE course_id={ph}", (course_id,))


def mark_category_draft_on_connection(conn, kind: str, category_id: str) -> None:
    if not category_id:
        return
    ph = common_db.placeholder(kind)
    conn.execute(
        f"UPDATE quiz_categories SET review_status={ph},reviewer_name={ph},reviewed_at={ph},"
        f"published_at={ph},publication_id={ph},publication_hash={ph},active={ph} WHERE id={ph}",
        ("draft", "", "", "", "", "", False if kind == "postgres" else 0, category_id),
    )


def mark_category_draft(category_id: str) -> None:
    with common_db.transaction() as (conn, kind):
        mark_category_draft_on_connection(conn, kind, category_id)


def next_question_sort_order(conn, kind: str, category_id: str) -> int:
    ph = common_db.placeholder(kind)
    row = conn.execute(
        f"SELECT COALESCE(MAX(sort_order),-1) AS m FROM quiz_questions WHERE quiz_category_id={ph}",
        (category_id,),
    ).fetchone()
    current = dict(row).get("m", -1) if row is not None else -1
    return int(current if current is not None else -1) + 1


def insert_runtime_question_on_connection(conn, kind: str, values: Mapping[str, Any]) -> None:
    ph = common_db.placeholder(kind)
    columns = (
        "id", "quiz_category_id", "tag", "question", "question_type", "difficulty",
        "image_url", "options", "correct", "answer_config", "explanation", "sort_order", "active",
    )
    data = dict(values)
    data["active"] = bool(data.get("active", True)) if kind == "postgres" else int(bool(data.get("active", True)))
    conn.execute(
        f"INSERT INTO quiz_questions ({','.join(columns)}) VALUES ({','.join([ph] * len(columns))})",
        tuple(data.get(column) for column in columns),
    )


def get_questions_by_ids_on_connection(conn, kind: str, question_ids: list[str]) -> dict[str, dict]:
    if not question_ids:
        return {}
    ph = common_db.placeholder(kind)
    placeholders = ",".join([ph] * len(question_ids))
    rows = conn.execute(
        f"SELECT * FROM quiz_questions WHERE id IN ({placeholders})",
        tuple(question_ids),
    ).fetchall()
    projected = [question_row_to_dict(row) for row in rows]
    return {str(item.get("id") or ""): item for item in projected}


def update_runtime_question_on_connection(
    conn,
    kind: str,
    question_id: str,
    normalized: Mapping[str, Any],
) -> None:
    ph = common_db.placeholder(kind)
    values = (
        normalized["tag"], normalized["question"], normalized["questionType"], normalized["difficulty"],
        normalized["imageUrl"], json.dumps(normalized["options"], ensure_ascii=False), normalized["correct"],
        json.dumps(normalized["answerConfig"], ensure_ascii=False), normalized["explanation"],
        normalized["active"] if kind == "postgres" else int(bool(normalized["active"])), question_id,
    )
    conn.execute(
        f"UPDATE quiz_questions SET tag={ph},question={ph},question_type={ph},difficulty={ph},image_url={ph},"
        f"options={ph},correct={ph},answer_config={ph},explanation={ph},active={ph} WHERE id={ph}",
        values,
    )


def delete_questions_on_connection(conn, kind: str, question_ids: list[str]) -> set[str]:
    if not question_ids:
        return set()
    ph = common_db.placeholder(kind)
    placeholders = ",".join([ph] * len(question_ids))
    rows = conn.execute(
        f"SELECT DISTINCT quiz_category_id FROM quiz_questions WHERE id IN ({placeholders})",
        tuple(question_ids),
    ).fetchall()
    category_ids = {str(dict(row).get("quiz_category_id") or "") for row in rows if dict(row).get("quiz_category_id")}
    conn.execute(f"DELETE FROM quiz_questions WHERE id IN ({placeholders})", tuple(question_ids))
    return category_ids


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
