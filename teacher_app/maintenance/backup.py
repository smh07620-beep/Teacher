"""Canonical logical backup/restore implementation.

HTTP/auth/elevation compatibility remains in root ``backup_restore.py`` while
archive validation and persistence ownership live here.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import io
import json
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

from teacher_app.common import db as common_db
from teacher_app.common.auth import normalize_roles

BACKUP_FORMAT = "teacher-backup-v1"
DEFAULT_TABLES = (
    "user_accounts", "courses", "quiz_categories", "quiz_questions",
    "exam_records", "materials", "material_progress", "learning_assignments",
    "material_versions", "pgy_assignments", "pgy_assignment_audit",
    "exam_attempts", "schema_migrations", "learning_progress",
    "material_text_index", "media_processing_jobs", "atlas_import_previews",
    "audit_events", "external_media", "question_versions",
    "question_attempt_analytics",
)


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def app_version() -> str:
    try:
        value = Path(__file__).resolve().parents[2].joinpath("VERSION").read_text(encoding="utf-8").strip()
        return value or "unknown"
    except Exception:
        return "unknown"


@contextmanager
def _read_scope(connection_factory: Callable | None = None):
    if connection_factory is None:
        with common_db.read_connection() as pair:
            yield pair
        return
    conn, kind = connection_factory()
    try:
        yield conn, kind
    finally:
        conn.close()


@contextmanager
def _write_scope(connection_factory: Callable | None = None):
    if connection_factory is None:
        with common_db.transaction() as pair:
            yield pair
        return
    conn, kind = connection_factory()
    try:
        if kind == "postgres" and hasattr(conn, "transaction"):
            with conn.transaction():
                yield conn, kind
        else:
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

