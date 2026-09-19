"""Canonical assessment/category and Question Bank data access."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Any, Mapping

from teacher_app.common import db as common_db
from teacher_app.common import scope


_QUESTION_VERSION_FIELDS = (
    "quizCategoryId",
    "tag",
    "question",
    "questionType",
    "difficulty",
    "imageUrl",
    "options",
    "correct",
    "answerConfig",
    "explanation",
    "domain",
    "topic",
    "subtopic",
    "learningObjective",
    "cognitiveLevel",
    "tags",
    "sourceMaterialId",
    "reviewSource",
)

_QUESTION_VERSION_ALIASES = {
    "quizCategoryId": ("quizCategoryId", "quiz_category_id"),
    "questionType": ("questionType", "question_type"),
    "imageUrl": ("imageUrl", "image_url"),
    "answerConfig": ("answerConfig", "answer_config"),
    "learningObjective": ("learningObjective", "learning_objective"),
    "cognitiveLevel": ("cognitiveLevel", "cognitive_level"),
    "sourceMaterialId": ("sourceMaterialId", "source_material_id"),
    "reviewSource": ("reviewSource", "review_source"),
}

_QUESTION_VERSION_JSON_FIELDS = {
    "options": [],
    "answerConfig": {},
    "tags": [],
    "reviewSource": {},
}


def _utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _json_decode(value: Any, fallback: Any) -> Any:
    if isinstance(value, type(fallback)):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return fallback
    return fallback


def _mapping_value(data: Mapping[str, Any], key: str, default: Any = "") -> Any:
    for alias in _QUESTION_VERSION_ALIASES.get(key, (key,)):
        if alias in data:
            return data.get(alias)
    return data.get(key, default)


def question_version_snapshot(row: Mapping[str, Any]) -> dict[str, Any]:
    """Canonical immutable content payload used for question version hashes.

    Workflow-only fields (review status, reviewer, active state, sort order) are
    intentionally excluded so reviewing/retiring a question does not create a
    new content version.
    """

    data = dict(row or {})
    snapshot: dict[str, Any] = {
        "id": str(data.get("id") or ""),
        "version": max(1, int(data.get("version", 1) or 1)),
    }
    for key in _QUESTION_VERSION_FIELDS:
        fallback = _QUESTION_VERSION_JSON_FIELDS.get(key, "")
        value = _mapping_value(data, key, fallback)
        if key in _QUESTION_VERSION_JSON_FIELDS:
            value = _json_decode(value, fallback)
            if not isinstance(value, type(fallback)):
                value = fallback
        elif key == "correct":
            try:
                value = int(value or 0)
            except (TypeError, ValueError):
                value = 0
        else:
            value = str(value or "")
        snapshot[key] = value
    return snapshot


def question_content_hash(row: Mapping[str, Any]) -> str:
    snapshot = question_version_snapshot(row)
    snapshot.pop("version", None)
    canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _column_exists(conn, kind: str, table: str, column: str) -> bool:
    if kind == "postgres":
        row = conn.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema=current_schema() AND table_name=%s AND column_name=%s",
            (table, column),
        ).fetchone()
        return bool(row)
    return any(str(row[1]) == column for row in conn.execute(f"PRAGMA table_info({table})").fetchall())


def _table_columns(conn, kind: str, table: str) -> set[str]:
    if kind == "postgres":
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema=current_schema() AND table_name=%s",
            (table,),
        ).fetchall()
        return {str(dict(row).get("column_name") or "") for row in rows}
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _question_versions_available(conn, kind: str) -> bool:
    return bool(_table_columns(conn, kind, "question_versions"))


def _insert_question_version_on_connection(
    conn,
    kind: str,
    row: Mapping[str, Any],
    *,
    created_at: str = "",
    created_by: str = "",
    change_reason: str = "content",
) -> bool:
    if not row or not _question_versions_available(conn, kind):
        return False
    question_id = str(row.get("id") or "").strip()
    if not question_id:
        return False
    version = max(1, int(row.get("version", 1) or 1))
    category_id = str(_mapping_value(row, "quizCategoryId", "") or "")
    group_key = ""
    if category_id and _table_columns(conn, kind, "quiz_categories"):
        ph = common_db.placeholder(kind)
        category_row = conn.execute(
            f"SELECT group_key FROM quiz_categories WHERE id={ph}",
            (category_id,),
        ).fetchone()
        if category_row:
            try:
                group_key = str(dict(category_row).get("group_key") or "")
            except (TypeError, ValueError):
                group_key = str(category_row[0] or "")
    snapshot = question_version_snapshot(row)
    question_hash = question_content_hash(row)
    snapshot["questionHash"] = question_hash
    payload = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    ph = common_db.placeholder(kind)
    payload_mark = f"{ph}::jsonb" if kind == "postgres" else ph
    if kind == "postgres":
        cursor = conn.execute(
            "INSERT INTO question_versions"
            "(question_id,version,question_hash,quiz_category_id,group_key,snapshot,created_at,created_by,change_reason) "
            f"VALUES({ph},{ph},{ph},{ph},{ph},{payload_mark},{ph},{ph},{ph}) "
            "ON CONFLICT(question_id,version) DO NOTHING",
            (
                question_id,
                version,
                question_hash,
                category_id,
                group_key,
                payload,
                str(created_at or row.get("updated_at") or _utcnow()),
                str(created_by or "")[:100],
                str(change_reason or "content")[:80],
            ),
        )
    else:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO question_versions"
            "(question_id,version,question_hash,quiz_category_id,group_key,snapshot,created_at,created_by,change_reason) "
            f"VALUES({','.join([ph] * 9)})",
            (
                question_id,
                version,
                question_hash,
                category_id,
                group_key,
                payload,
                str(created_at or row.get("updated_at") or _utcnow()),
                str(created_by or "")[:100],
                str(change_reason or "content")[:80],
            ),
        )
    return int(getattr(cursor, "rowcount", 0) or 0) > 0


def backfill_question_versions_on_connection(conn, kind: str, *, created_at: str = "") -> int:
    """Create one immutable baseline version for every existing live question."""

    if not _question_versions_available(conn, kind) or not _table_columns(conn, kind, "quiz_questions"):
        return 0
    rows = conn.execute("SELECT * FROM quiz_questions").fetchall()
    inserted = 0
    for row in rows:
        inserted += int(
            _insert_question_version_on_connection(
                conn,
                kind,
                dict(row),
                created_at=created_at,
                change_reason="baseline",
            )
        )
    return inserted


def list_question_versions(question_id: str, limit: int = 100) -> list[dict[str, Any]]:
    limit = max(1, min(200, int(limit or 100)))
    with common_db.read_connection() as (conn, kind):
        if not _question_versions_available(conn, kind):
            return []
        ph = common_db.placeholder(kind)
        rows = conn.execute(
            f"SELECT question_id,version,question_hash,quiz_category_id,group_key,snapshot,created_at,created_by,change_reason "
            f"FROM question_versions WHERE question_id={ph} ORDER BY version DESC LIMIT {limit}",
            (question_id,),
        ).fetchall()
    output: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["snapshot"] = _json_decode(item.get("snapshot"), {})
        output.append(item)
    return output


def get_question_version(question_id: str, version: int) -> dict[str, Any] | None:
    with common_db.read_connection() as (conn, kind):
        if not _question_versions_available(conn, kind):
            return None
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT question_id,version,question_hash,quiz_category_id,group_key,snapshot,created_at,created_by,change_reason "
            f"FROM question_versions WHERE question_id={ph} AND version={ph}",
            (question_id, max(1, int(version or 1))),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["snapshot"] = _json_decode(item.get("snapshot"), {})
    return item


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
    data["reviewerTitle"] = str(data.pop("reviewer_title", "") or "")
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
    fields = [
        "title", "description", "active", "blind_mode", "draw_count", "passing_score",
        "audience", "course_id", "draw_rules", "review_status", "reviewer_name",
        "reviewed_at", "published_at",
    ]
    with common_db.transaction() as (conn, kind):
        if _column_exists(conn, kind, "quiz_categories", "reviewer_title"):
            fields.insert(fields.index("reviewed_at"), "reviewer_title")
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


def mark_category_reviewed(category_id: str, *, reviewer: str, reviewer_title: str, reviewed_at: str) -> None:
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        active = False if kind == "postgres" else 0
        if _column_exists(conn, kind, "quiz_categories", "reviewer_title"):
            conn.execute(
                f"UPDATE quiz_categories SET review_status={ph},reviewer_name={ph},reviewer_title={ph},reviewed_at={ph},active={ph} WHERE id={ph}",
                ("approved", reviewer, reviewer_title, reviewed_at, active, category_id),
            )
        else:
            conn.execute(
                f"UPDATE quiz_categories SET review_status={ph},reviewer_name={ph},reviewed_at={ph},active={ph} WHERE id={ph}",
                ("approved", reviewer, reviewed_at, active, category_id),
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
    active = False if kind == "postgres" else 0
    if _column_exists(conn, kind, "quiz_categories", "reviewer_title"):
        conn.execute(
            f"UPDATE quiz_categories SET review_status={ph},reviewer_name={ph},reviewer_title={ph},reviewed_at={ph},"
            f"published_at={ph},publication_id={ph},publication_hash={ph},active={ph} WHERE id={ph}",
            ("draft", "", "", "", "", "", "", active, category_id),
        )
    else:
        conn.execute(
            f"UPDATE quiz_categories SET review_status={ph},reviewer_name={ph},reviewed_at={ph},"
            f"published_at={ph},publication_id={ph},publication_hash={ph},active={ph} WHERE id={ph}",
            ("draft", "", "", "", "", "", active, category_id),
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
    row = conn.execute(
        f"SELECT * FROM quiz_questions WHERE id={ph}",
        (str(data.get("id") or ""),),
    ).fetchone()
    if row:
        _insert_question_version_on_connection(
            conn,
            kind,
            dict(row),
            change_reason="create",
        )


def reset_question_review_on_connection(
    conn,
    kind: str,
    question_ids: list[str],
    *,
    origin: str | None = None,
) -> None:
    """Reset optional 6.8 Question Bank workflow columns after content mutation."""
    if not question_ids:
        return
    if kind == "postgres":
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema=current_schema() AND table_name='quiz_questions'"
        ).fetchall()
        columns = {str(dict(row).get("column_name") or "").lower() for row in rows}
    else:
        columns = {
            str(row[1]).lower()
            for row in conn.execute("PRAGMA table_info(quiz_questions)").fetchall()
        }
    if "status" not in columns:
        return

    ph = common_db.placeholder(kind)
    assignments = [f"status={ph}"]
    values: list[Any] = ["draft"]
    if "reviewed_by" in columns:
        assignments.append(f"reviewed_by={ph}")
        values.append("")
    if "reviewed_at" in columns:
        assignments.append(f"reviewed_at={ph}")
        values.append("")
    if origin is not None and "origin" in columns:
        assignments.append(f"origin={ph}")
        values.append(str(origin or "manual")[:40])
    placeholders = ",".join([ph] * len(question_ids))
    conn.execute(
        f"UPDATE quiz_questions SET {','.join(assignments)} WHERE id IN ({placeholders})",
        tuple(values) + tuple(question_ids),
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
    before_row = conn.execute(
        f"SELECT * FROM quiz_questions WHERE id={ph}",
        (question_id,),
    ).fetchone()
    before = dict(before_row) if before_row else {}
    before_hash = question_content_hash(before) if before else ""
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
    after_row = conn.execute(
        f"SELECT * FROM quiz_questions WHERE id={ph}",
        (question_id,),
    ).fetchone()
    after = dict(after_row) if after_row else {}
    if after and before_hash != question_content_hash(after):
        columns = _table_columns(conn, kind, "quiz_questions")
        if "version" in columns:
            conn.execute(
                f"UPDATE quiz_questions SET version=version+1 WHERE id={ph}",
                (question_id,),
            )
            after_row = conn.execute(
                f"SELECT * FROM quiz_questions WHERE id={ph}",
                (question_id,),
            ).fetchone()
            after = dict(after_row) if after_row else after
        _insert_question_version_on_connection(
            conn,
            kind,
            after,
            change_reason="content_edit",
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
        row = conn.execute(
            f"SELECT * FROM quiz_questions WHERE id={ph}",
            (str(values.get("id") or ""),),
        ).fetchone()
        if row:
            _insert_question_version_on_connection(
                conn,
                kind,
                dict(row),
                created_at=str(values.get("updated_at") or ""),
                change_reason="create",
            )


def update_bank_question(question_id: str, values: Mapping[str, Any]) -> dict | None:
    columns = (
        "question", "options", "correct", "explanation", "topic", "subtopic",
        "learning_objective", "difficulty", "cognitive_level", "tags",
        "source_material_id", "review_source", "status", "origin", "updated_at",
        "reviewed_by", "reviewed_at",
    )
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        before_row = conn.execute(
            f"SELECT * FROM quiz_questions WHERE id={ph}",
            (question_id,),
        ).fetchone()
        before = dict(before_row) if before_row else {}
        before_hash = question_content_hash(before) if before else ""
        conn.execute(
            "UPDATE quiz_questions SET "
            + ",".join(f"{column}={ph}" for column in columns)
            + f" WHERE id={ph}",
            tuple(values.get(column) for column in columns) + (question_id,),
        )
        row = conn.execute(
            f"SELECT * FROM quiz_questions WHERE id={ph}",
            (question_id,),
        ).fetchone()
        current = dict(row) if row else {}
        if current and before_hash != question_content_hash(current):
            if "version" in _table_columns(conn, kind, "quiz_questions"):
                conn.execute(
                    f"UPDATE quiz_questions SET version=version+1 WHERE id={ph}",
                    (question_id,),
                )
                row = conn.execute(
                    f"SELECT * FROM quiz_questions WHERE id={ph}",
                    (question_id,),
                ).fetchone()
                current = dict(row) if row else current
            _insert_question_version_on_connection(
                conn,
                kind,
                current,
                created_at=str(values.get("updated_at") or ""),
                change_reason="content_edit",
            )
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
                f"UPDATE quiz_questions SET status={ph},reviewed_by={ph},reviewed_at={ph},updated_at={ph} WHERE id={ph} AND status='draft'",
                ("reviewed", username, stamp, stamp, question_id),
            )
        elif decision == "return":
            cursor = conn.execute(
                f"UPDATE quiz_questions SET status={ph},reviewed_by={ph},reviewed_at={ph},updated_at={ph} WHERE id={ph}",
                ("draft", "", "", stamp, question_id),
            )
        else:
            cursor = conn.execute(
                f"UPDATE quiz_questions SET status={ph},updated_at={ph} WHERE id={ph}",
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


def current_question_version_identity(question_id: str) -> dict[str, Any]:
    row = get_bank_question(question_id)
    if not row:
        return {"version": 1, "questionHash": ""}
    return {
        "version": max(1, int(row.get("version", 1) or 1)),
        "questionHash": question_content_hash(row),
    }


def list_question_attempt_analytics(
    question_id: str,
    *,
    version: int | None = None,
    question_hash: str = "",
) -> list[dict]:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        columns = _table_columns(conn, kind, "question_attempt_analytics")
        if not columns:
            return []
        selected = ["selected_option", "is_correct"]
        for optional in ("attempt_score", "response_seconds", "question_version", "question_hash"):
            if optional in columns:
                selected.append(optional)
        clauses = [f"question_id={ph}"]
        params: list[Any] = [question_id]
        if version is not None and "question_version" in columns:
            clauses.append(f"question_version={ph}")
            params.append(max(1, int(version or 1)))
        if question_hash and "question_hash" in columns:
            clauses.append(f"question_hash={ph}")
            params.append(str(question_hash))
        rows = conn.execute(
            f"SELECT {','.join(selected)} FROM question_attempt_analytics WHERE {' AND '.join(clauses)}",
            tuple(params),
        ).fetchall()
    return [dict(row) for row in rows]


def record_question_attempt_analytics_on_connection(
    conn,
    kind: str,
    *,
    attempt_id: str,
    questions: list[Mapping[str, Any]],
    answers: list[Any],
    answer_details: list[Mapping[str, Any]],
    attempt_score: float,
    response_timings: list[Any] | None,
    created_at: str,
) -> int:
    """Persist non-authoritative item analytics in the exam submission transaction.

    Timing comes from the browser and is therefore analytics-only.  It never
    participates in grading, access control or attempt state transitions.
    """
    columns = _table_columns(conn, kind, "question_attempt_analytics")
    required = {"question_id", "attempt_id", "selected_option", "is_correct", "created_at"}
    if not required.issubset(columns):
        return 0
    timings = response_timings if isinstance(response_timings, list) else []
    ph = common_db.placeholder(kind)
    inserted = 0
    for index, question in enumerate(questions):
        detail = answer_details[index] if index < len(answer_details) else {}
        is_correct = detail.get("isCorrect")
        question_id = str(question.get("id") or "").strip()
        if not question_id or is_correct is None:
            continue
        answer = answers[index] if index < len(answers) else None
        if isinstance(answer, (list, dict)):
            selected_option = json.dumps(answer, ensure_ascii=False, separators=(",", ":"))
        else:
            selected_option = str(answer if answer is not None else "")[:4000]
        names = ["question_id", "attempt_id", "selected_option", "is_correct", "created_at"]
        values: list[Any] = [
            question_id,
            attempt_id,
            selected_option,
            bool(is_correct) if kind == "postgres" else int(bool(is_correct)),
            created_at,
        ]
        if "attempt_score" in columns:
            names.append("attempt_score")
            values.append(max(0.0, min(100.0, float(attempt_score or 0))))
        if "response_seconds" in columns:
            names.append("response_seconds")
            try:
                seconds = float(timings[index]) if index < len(timings) else 0.0
            except (TypeError, ValueError):
                seconds = 0.0
            values.append(max(0.0, min(86400.0, seconds)))
        if "question_version" in columns:
            names.append("question_version")
            values.append(max(1, int(question.get("version", 1) or 1)))
        if "question_hash" in columns:
            names.append("question_hash")
            values.append(str(question.get("questionHash") or question_content_hash(question))[:64])
        marks = ",".join([ph] * len(names))
        update_names = [name for name in names if name not in {"question_id", "attempt_id"}]
        assignments = ",".join(f"{name}=excluded.{name}" for name in update_names)
        conn.execute(
            f"INSERT INTO question_attempt_analytics({','.join(names)}) VALUES({marks}) "
            f"ON CONFLICT(question_id,attempt_id) DO UPDATE SET {assignments}",
            tuple(values),
        )
        inserted += 1
    return inserted


def get_bank_question_correct(question_id: str) -> Any:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT correct FROM quiz_questions WHERE id={ph}",
            (question_id,),
        ).fetchone()
    return dict(row).get("correct") if row else None


def get_question_version_correct(question_id: str, version: int | None = None) -> Any:
    if version is None:
        return get_bank_question_correct(question_id)
    stored = get_question_version(question_id, version)
    snapshot = (stored or {}).get("snapshot") if stored else None
    if isinstance(snapshot, dict) and "correct" in snapshot:
        return snapshot.get("correct")
    return None


def get_question_version_options(question_id: str, version: int | None = None) -> list[Any]:
    if version is not None:
        stored = get_question_version(question_id, version)
        snapshot = (stored or {}).get("snapshot") if stored else None
        if isinstance(snapshot, dict) and isinstance(snapshot.get("options"), list):
            return list(snapshot.get("options") or [])
        return []
    row = get_bank_question(question_id) or {}
    return list(_json_decode(row.get("options"), []))
