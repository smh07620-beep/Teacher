"""Canonical one-time data migrations retained from the legacy application.

These migrations intentionally own only historical data bootstrap behavior.
Base/domain schema creation belongs to the canonical domain schema owners; the
small ``app_meta`` table used to remember one-time data migrations lives here.
"""
from __future__ import annotations

import datetime
import json
import logging
import uuid
from pathlib import Path
from typing import Any, Callable

from teacher_app.common import db as common_db
from teacher_app.config import DATA_DIR


ConnectionFactory = Callable[[], tuple[Any, str]]

BUILTIN_QUIZ_SEED_PATH = DATA_DIR / "builtin_quiz_seed.json"
BIO_QUIZ_MIGRATION_KEY = "v5.3.7-bio-quiz-migrated"
V540_EXAM_SETTINGS_MIGRATION_KEY = "v5.4.0-exam-settings-migrated"

_LOG = logging.getLogger(__name__)


def _open_connection(connection_factory: ConnectionFactory | None):
    factory = connection_factory or common_db.get_connection
    return factory()


def _ensure_app_meta(conn) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS app_meta "
        "(meta_key TEXT PRIMARY KEY, meta_value TEXT NOT NULL DEFAULT '')"
    )


def _meta_value(conn, kind: str, key: str):
    ph = common_db.placeholder(kind)
    return conn.execute(
        f"SELECT meta_value FROM app_meta WHERE meta_key={ph}",
        (key,),
    ).fetchone()


def _set_meta(conn, kind: str, key: str, value: str) -> None:
    if kind == "postgres":
        conn.execute(
            "INSERT INTO app_meta (meta_key,meta_value) VALUES (%s,%s) "
            "ON CONFLICT (meta_key) DO UPDATE SET meta_value=EXCLUDED.meta_value",
            (key, value),
        )
        return
    conn.execute(
        "INSERT OR REPLACE INTO app_meta (meta_key,meta_value) VALUES (?,?)",
        (key, value),
    )


def seed_builtin_bio_quizzes(
    connection_factory: ConnectionFactory | None = None,
    *,
    seed_path: Path | str | None = None,
) -> None:
    """Run the V5.3.7 built-in biochemistry quiz migration once.

    A completed marker is authoritative: later administrator edits or deletions
    must not cause the historical built-in quizzes to be inserted again.
    Missing or unreadable seed data remains a best-effort startup condition and
    therefore leaves the migration unmarked for a later retry.
    """
    source = Path(seed_path) if seed_path is not None else BUILTIN_QUIZ_SEED_PATH
    if not source.exists():
        return
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except Exception as exc:
        _LOG.warning("builtin quiz seed load failed: %s", exc)
        return

    conn, kind = _open_connection(connection_factory)
    ph = common_db.placeholder(kind)
    try:
        _ensure_app_meta(conn)
        if _meta_value(conn, kind, BIO_QUIZ_MIGRATION_KEY):
            return

        for cat in payload.get("categories", []):
            cid = str(cat.get("id", "")).strip()
            if not cid:
                continue
            exists = conn.execute(
                f"SELECT id FROM quiz_categories WHERE id={ph}",
                (cid,),
            ).fetchone()
            if exists:
                continue

            title = str(cat.get("title", cid))[:255]
            desc = str(cat.get("desc", ""))[:1000]
            order = int(cat.get("sortOrder", 0) or 0)
            date_added = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            if kind == "postgres":
                conn.execute(
                    "INSERT INTO quiz_categories "
                    "(id,group_key,training_area,course_id,title,description,sort_order,date_added,active) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (cid, "grpBio", "internal", "", title, desc, order, date_added, True),
                )
            else:
                conn.execute(
                    "INSERT INTO quiz_categories "
                    "(id,group_key,training_area,course_id,title,description,sort_order,date_added,active) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (cid, "grpBio", "internal", "", title, desc, order, date_added, 1),
                )

            for question in cat.get("questions", []):
                values = (
                    str(question.get("id") or f"q-{uuid.uuid4().hex[:12]}"),
                    cid,
                    str(question.get("tag", "一般"))[:100],
                    str(question.get("question", "")).strip(),
                    str(question.get("questionType", "choice")),
                    str(question.get("imageUrl", ""))[:1000],
                    json.dumps(question.get("options", []), ensure_ascii=False),
                    int(question.get("correct", 0) or 0),
                    str(question.get("explanation", "")),
                    int(question.get("sortOrder", 0) or 0),
                )
                if kind == "postgres":
                    conn.execute(
                        "INSERT INTO quiz_questions "
                        "(id,quiz_category_id,tag,question,question_type,image_url,options,correct,explanation,sort_order,active) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)",
                        values,
                    )
                else:
                    conn.execute(
                        "INSERT INTO quiz_questions "
                        "(id,quiz_category_id,tag,question,question_type,image_url,options,correct,explanation,sort_order,active) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,1)",
                        values,
                    )

        _set_meta(
            conn,
            kind,
            BIO_QUIZ_MIGRATION_KEY,
            datetime.datetime.now().isoformat(),
        )
    except Exception as exc:
        _LOG.exception("builtin quiz seed failed: %s", exc)
    finally:
        conn.close()


def migrate_v540_exam_settings(
    connection_factory: ConnectionFactory | None = None,
) -> None:
    """Preserve the V5.3.x default of drawing 10 questions for existing exams."""
    conn, kind = _open_connection(connection_factory)
    try:
        _ensure_app_meta(conn)
        if _meta_value(conn, kind, V540_EXAM_SETTINGS_MIGRATION_KEY):
            return
        conn.execute(
            "UPDATE quiz_categories SET draw_count=10 WHERE COALESCE(draw_count,0)=0"
        )
        _set_meta(
            conn,
            kind,
            V540_EXAM_SETTINGS_MIGRATION_KEY,
            datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
    finally:
        conn.close()


def init_builtin_meta() -> None:
    """Compatibility no-op; the material catalog treats missing metadata as empty."""
    return None


def run_legacy_data_migrations(
    connection_factory: ConnectionFactory | None = None,
    *,
    seed_path: Path | str | None = None,
) -> None:
    """Run historical data migrations in their required compatibility order."""
    seed_builtin_bio_quizzes(connection_factory, seed_path=seed_path)
    migrate_v540_exam_settings(connection_factory)
    init_builtin_meta()


__all__ = [
    "BIO_QUIZ_MIGRATION_KEY",
    "BUILTIN_QUIZ_SEED_PATH",
    "V540_EXAM_SETTINGS_MIGRATION_KEY",
    "init_builtin_meta",
    "migrate_v540_exam_settings",
    "run_legacy_data_migrations",
    "seed_builtin_bio_quizzes",
]
