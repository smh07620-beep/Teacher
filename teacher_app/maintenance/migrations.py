"""Teacher schema migration registry.

This owns the release migration baseline and applies each registered migration
exactly once. Shared tables should be created here instead of by runtime adapters.
"""
from __future__ import annotations

import datetime as dt
import json
from typing import Any, Callable

from teacher_app.common import db as common_db
from teacher_app.common.auth import normalize_roles

MIGRATIONS: list[tuple[str, Callable]] = []


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def migration(version: str):
    def deco(fn: Callable):
        MIGRATIONS.append((version, fn))
        return fn
    return deco


@migration("0064-baseline")
def _baseline(conn, kind: str) -> None:
    """Create the canonical account table required by every later release."""
    active_type = "BOOLEAN" if kind == "postgres" else "INTEGER"
    active_default = "TRUE" if kind == "postgres" else "1"
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS user_accounts (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            emp_id TEXT NOT NULL UNIQUE,
            role TEXT NOT NULL DEFAULT 'learner',
            preferred_area TEXT NOT NULL DEFAULT 'internal',
            preferred_group TEXT NOT NULL DEFAULT 'grpBio',
            active {active_type} NOT NULL DEFAULT {active_default},
            session_version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_login_at TEXT NOT NULL DEFAULT ''
        )
        """
    )


def ensure_user_accounts_base(base) -> None:
    """Explicit compatibility helper for tests/maintenance using the 6.4 schema."""
    conn, kind = base._db_conn()
    try:
        _baseline(conn, kind)
    finally:
        conn.close()


@migration("0065-architecture")
def _architecture_65(conn, kind: str) -> None:
    """6.5 modular-architecture marker.

    M1-M7 intentionally preserve the existing production schema and
    production entrypoint.  No destructive DDL is required for this release.
    """
    return None


def _row_value(row: Any, key: str, index: int = 0) -> Any:
    """Read SQLite rows, psycopg mapping rows, and lightweight test rows."""
    try:
        return dict(row).get(key)
    except (TypeError, ValueError):
        try:
            return row[key]
        except (KeyError, TypeError, IndexError):
            return row[index]


def _table_exists(conn, kind: str, table: str) -> bool:
    if kind == "postgres":
        row = conn.execute(
            """
            SELECT 1 AS present
            FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_name = %s
            """,
            (table,),
        ).fetchone()
        return bool(row)

    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row)


def _columns(conn, kind: str, table: str) -> set[str]:
    if kind == "postgres":
        rows = conn.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = %s
            """,
            (table,),
        ).fetchall()
        return {
            str(_row_value(row, "column_name")).lower()
            for row in rows
        }

    return {
        str(_row_value(row, "name", 1)).lower()
        for row in conn.execute(
            f"PRAGMA table_info({table})"
        ).fetchall()
    }


def _add_columns(
    conn,
    kind: str,
    table: str,
    columns: dict[str, str],
) -> set[str]:
    """Apply only missing additive columns; no table or row is replaced."""
    if not _table_exists(conn, kind, table):
        return set()

    existing = _columns(conn, kind, table)
    added: set[str] = set()

    for name, definition in columns.items():
        if name in existing:
            continue
        if kind == "postgres":
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {definition}"
            )
        else:
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN {definition}"
            )
        added.add(name)

    return added


def _roles_json(value: Any, primary_role: Any) -> str:
    """Keep the legacy role first while persisting the normalized role set."""
    return json.dumps(
        normalize_roles(value, primary=primary_role),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _backfill_legacy_user_roles(conn, kind: str) -> None:
    if not _table_exists(conn, kind, "user_accounts"):
        return
    if "roles_json" not in _columns(conn, kind, "user_accounts"):
        return

    rows = conn.execute(
        "SELECT username, role, roles_json FROM user_accounts"
    ).fetchall()
    ph = "%s" if kind == "postgres" else "?"

    for row in rows:
        username = str(_row_value(row, "username") or "").strip()
        stored = _row_value(row, "roles_json", 2)
        raw = str(stored or "").strip()
        if not username or raw not in {"", "[]"}:
            continue

        conn.execute(
            f"""
            UPDATE user_accounts
            SET roles_json={ph}
            WHERE username={ph}
              AND (roles_json IS NULL OR TRIM(roles_json) IN ('', '[]'))
            """,
            (
                _roles_json(None, _row_value(row, "role", 1)),
                username,
            ),
        )


@migration("0066-additive-rbac-pgy-signing")
def _additive_rbac_pgy_signing_66(conn, kind: str) -> None:
    """Formal 6.6 schema source for the additive M1 signing/RBAC fields.

    The migration deliberately leaves legacy columns and rows in place.  Old
    assignments get the ``legacy`` default and keep the 6.5 transition flow;
    the 6.6 create route explicitly selects ``single`` for new assignments.
    """
    _add_columns(
        conn,
        kind,
        "user_accounts",
        {
            "roles_json": "roles_json TEXT NOT NULL DEFAULT '[]'",
        },
    )
    _backfill_legacy_user_roles(conn, kind)
    _add_columns(conn, kind, "pgy_assignments", {"sign_mode": "sign_mode TEXT NOT NULL DEFAULT 'legacy'", "first_signature": "first_signature TEXT NOT NULL DEFAULT '{}'", "second_signature": "second_signature TEXT NOT NULL DEFAULT '{}'"})


@migration("0067-smart-learning-content")
def _smart_learning_67(conn, kind: str) -> None:
    """Additive/idempotent learning metadata; no legacy row is overwritten."""
    boolean = "BOOLEAN" if kind == "postgres" else "INTEGER"
    default_false = "FALSE" if kind == "postgres" else "0"
    conn.execute(f"CREATE TABLE IF NOT EXISTS learning_progress (material_id TEXT NOT NULL, username TEXT NOT NULL, position TEXT NOT NULL DEFAULT '{{}}', progress REAL NOT NULL DEFAULT 0, completed {boolean} NOT NULL DEFAULT {default_false}, last_viewed_at TEXT NOT NULL DEFAULT '', completed_at TEXT NOT NULL DEFAULT '', PRIMARY KEY(material_id,username))")
    conn.execute("CREATE TABLE IF NOT EXISTS material_text_index (material_id TEXT NOT NULL,page_no INTEGER NOT NULL,title TEXT NOT NULL DEFAULT '',text TEXT NOT NULL DEFAULT '',indexed_at TEXT NOT NULL DEFAULT '',PRIMARY KEY(material_id,page_no))")
    conn.execute("CREATE TABLE IF NOT EXISTS media_processing_jobs (id TEXT PRIMARY KEY,material_id TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',failure_reason TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS atlas_import_previews (id TEXT PRIMARY KEY,material_id TEXT NOT NULL,payload TEXT NOT NULL DEFAULT '{}',status TEXT NOT NULL DEFAULT 'preview',created_at TEXT NOT NULL)")


@migration("0067-render-worker-shared-staging")
def _render_worker_shared_staging_67(conn, kind: str) -> None:
    """Add Scheme B metadata without re-running or overwriting the original 0067.

    Existing 6.7 databases may already have recorded 0067, so this separate
    additive marker upgrades them safely.  `material_jobs` remains the only
    queue; media_processing_jobs is linked supporting metadata for media jobs.
    """
    _add_columns(conn, kind, "material_jobs", {
        "staging_backend": "staging_backend TEXT NOT NULL DEFAULT 'local'",
        "staging_key": "staging_key TEXT NOT NULL DEFAULT ''",
        "original_name": "original_name TEXT NOT NULL DEFAULT ''",
    })
    _add_columns(conn, kind, "media_processing_jobs", {
        "material_job_id": "material_job_id TEXT NOT NULL DEFAULT ''",
    })


@migration("0067-b-free-local-worker")
def _b_free_local_worker_67(conn, kind: str) -> None:
    """Add B-Free control metadata; no data is replaced or removed."""
    boolean = "BOOLEAN" if kind == "postgres" else "INTEGER"
    default_false = "FALSE" if kind == "postgres" else "0"
    _add_columns(conn, kind, "material_jobs", {
        "worker_last_seen": "worker_last_seen TEXT NOT NULL DEFAULT ''",
        "cleanup_pending": f"cleanup_pending {boolean} NOT NULL DEFAULT {default_false}",
    })
    payload = "JSONB" if kind == "postgres" else "TEXT"
    conn.execute(f"CREATE TABLE IF NOT EXISTS material_worker_heartbeats (worker_id TEXT PRIMARY KEY,last_seen TEXT NOT NULL,capabilities {payload} NOT NULL DEFAULT '{{}}',current_job_id TEXT NOT NULL DEFAULT '')")
    conn.execute(f"CREATE TABLE IF NOT EXISTS material_upload_sessions (id TEXT PRIMARY KEY,job_id TEXT NOT NULL UNIQUE,material_id TEXT NOT NULL,staging_key TEXT NOT NULL,original_name TEXT NOT NULL,source_sha256 TEXT NOT NULL,source_bytes BIGINT NOT NULL,r2_upload_id TEXT NOT NULL,part_size BIGINT NOT NULL,expected_parts INTEGER NOT NULL,payload {payload} NOT NULL DEFAULT '{{}}',completed_parts {payload} NOT NULL DEFAULT '[]',status TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)")


@migration("0067-r2-free-budget-guard")
def _r2_free_budget_guard_67(conn, kind: str) -> None:
    """Create the additive R2 budget guard schema exactly once via migration."""
    boolean = "BOOLEAN" if kind == "postgres" else "INTEGER"
    default_bool = "TRUE" if kind == "postgres" else "1"
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS r2_upload_reservations ("
        "id TEXT PRIMARY KEY,upload_id TEXT NOT NULL UNIQUE,object_key TEXT NOT NULL UNIQUE,"
        "reserved_bytes BIGINT NOT NULL,status TEXT NOT NULL DEFAULT 'active',"
        "created_at TEXT NOT NULL,expires_at TEXT NOT NULL,released_at TEXT NOT NULL DEFAULT '',"
        "release_reason TEXT NOT NULL DEFAULT '')"
    )
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS r2_usage_ledger ("
        "id TEXT PRIMARY KEY,object_key TEXT NOT NULL UNIQUE,object_bytes BIGINT NOT NULL,"
        "uploaded_at TEXT NOT NULL,deleted_at TEXT NOT NULL DEFAULT '',"
        "multipart_parts INTEGER NOT NULL DEFAULT 0,estimated_operations BIGINT NOT NULL DEFAULT 0,"
        f"is_staging {boolean} NOT NULL DEFAULT {default_bool})"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_r2_upload_reservations_active "
        "ON r2_upload_reservations(status, expires_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_r2_usage_ledger_active "
        "ON r2_usage_ledger(deleted_at, uploaded_at)"
    )


@migration("0068-external-interactive-media")
def _external_interactive_media_68(conn, kind: str) -> None:
    """6.8 additive media, elevation and question-bank schema.

    This intentionally extends the established learning_progress and
    quiz_questions tables rather than creating competing stores.
    """
    boolean = "BOOLEAN" if kind == "postgres" else "INTEGER"
    default_false = "FALSE" if kind == "postgres" else "0"
    payload = "JSONB" if kind == "postgres" else "TEXT"
    _add_columns(conn, kind, "learning_progress", {
        "last_position_seconds": "last_position_seconds REAL NOT NULL DEFAULT 0",
        "duration": "duration REAL NOT NULL DEFAULT 0",
        "watched_buckets": "watched_buckets TEXT NOT NULL DEFAULT '[]'",
        "completion_threshold": "completion_threshold REAL NOT NULL DEFAULT 0.9",
        "updated_at": "updated_at TEXT NOT NULL DEFAULT ''",
    })
    _add_columns(conn, kind, "quiz_questions", {
        "domain": "domain TEXT NOT NULL DEFAULT ''", "topic": "topic TEXT NOT NULL DEFAULT ''",
        "subtopic": "subtopic TEXT NOT NULL DEFAULT ''", "learning_objective": "learning_objective TEXT NOT NULL DEFAULT ''",
        "cognitive_level": "cognitive_level TEXT NOT NULL DEFAULT 'understand'", "tags": "tags TEXT NOT NULL DEFAULT '[]'",
        "source_material_id": "source_material_id TEXT NOT NULL DEFAULT ''", "review_source": "review_source TEXT NOT NULL DEFAULT '{}'",
        "status": "status TEXT NOT NULL DEFAULT 'published'", "origin": "origin TEXT NOT NULL DEFAULT 'manual'",
        "version": "version INTEGER NOT NULL DEFAULT 1", "reviewed_by": "reviewed_by TEXT NOT NULL DEFAULT ''",
        "reviewed_at": "reviewed_at TEXT NOT NULL DEFAULT ''", "updated_at": "updated_at TEXT NOT NULL DEFAULT ''",
        "normalized_hash": "normalized_hash TEXT NOT NULL DEFAULT ''",
    })
    conn.execute(f"CREATE TABLE IF NOT EXISTS external_media (id TEXT PRIMARY KEY,material_id TEXT NOT NULL,provider TEXT NOT NULL,canonical_url TEXT NOT NULL,video_id TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(material_id))")
    conn.execute(f"CREATE TABLE IF NOT EXISTS admin_elevations (username TEXT PRIMARY KEY,elevated_at TEXT NOT NULL,expires_at TEXT NOT NULL,session_version INTEGER NOT NULL DEFAULT 0)")
    conn.execute(f"CREATE TABLE IF NOT EXISTS exam_blueprints (id TEXT PRIMARY KEY,quiz_category_id TEXT NOT NULL,question_count INTEGER NOT NULL,quotas {payload} NOT NULL DEFAULT '{{}}',exclude_recent INTEGER NOT NULL DEFAULT 0,created_by TEXT NOT NULL,created_at TEXT NOT NULL)")
    conn.execute(f"CREATE TABLE IF NOT EXISTS exam_blueprint_snapshots (id TEXT PRIMARY KEY,blueprint_id TEXT NOT NULL,quiz_category_id TEXT NOT NULL,questions {payload} NOT NULL,created_at TEXT NOT NULL,UNIQUE(blueprint_id))")
    conn.execute(f"CREATE TABLE IF NOT EXISTS question_attempt_analytics (question_id TEXT NOT NULL,attempt_id TEXT NOT NULL,selected_option TEXT NOT NULL DEFAULT '',is_correct {boolean} NOT NULL DEFAULT {default_false},created_at TEXT NOT NULL,PRIMARY KEY(question_id,attempt_id))")


@migration("0069-user-profile-titles")
def _user_profile_titles_69(conn, kind: str) -> None:
    """Presentation-only profile fields; role storage and password hashes stay untouched."""
    _add_columns(conn, kind, "user_accounts", {
        "professional_title": "professional_title TEXT NOT NULL DEFAULT ''",
        "responsibility_tags": "responsibility_tags TEXT NOT NULL DEFAULT '[]'",
    })


@migration("0070-material-search-and-atlas")
def _material_search_and_atlas_70(conn, kind: str) -> None:
    """Formal, additive resource search and Atlas records.

    Images remain in the configured material storage.  The database holds only
    a storage URL/key and metadata, never image bytes.  This migration is safe
    to apply repeatedly on both supported database engines.
    """
    boolean = "BOOLEAN" if kind == "postgres" else "INTEGER"
    default_false = "FALSE" if kind == "postgres" else "0"
    payload = "JSONB" if kind == "postgres" else "TEXT"
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS material_search_status ("
        "material_id TEXT PRIMARY KEY,status TEXT NOT NULL DEFAULT 'not_indexed',"
        "page_count INTEGER NOT NULL DEFAULT 0,last_indexed_at TEXT NOT NULL DEFAULT '',"
        "failure_reason TEXT NOT NULL DEFAULT '',source_kind TEXT NOT NULL DEFAULT '')"
    )
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS atlas_items ("
        "id TEXT PRIMARY KEY,category TEXT NOT NULL,group_key TEXT NOT NULL,"
        "title TEXT NOT NULL,image_url TEXT NOT NULL DEFAULT '',description TEXT NOT NULL DEFAULT '',"
        "tags TEXT NOT NULL DEFAULT '[]',differential_points TEXT NOT NULL DEFAULT '',"
        "teaching_notes TEXT NOT NULL DEFAULT '',difficulty TEXT NOT NULL DEFAULT 'general',"
        f"published {boolean} NOT NULL DEFAULT {default_false},source TEXT NOT NULL DEFAULT 'manual',"
        "source_material_id TEXT NOT NULL DEFAULT '',source_docx TEXT NOT NULL DEFAULT '',"
        "sort_order INTEGER NOT NULL DEFAULT 0,annotation_json " + payload + " NOT NULL DEFAULT '{}',"
        "created_at TEXT NOT NULL,updated_at TEXT NOT NULL,created_by TEXT NOT NULL DEFAULT '',"
        "updated_by TEXT NOT NULL DEFAULT '')"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_atlas_items_visibility ON atlas_items(group_key,published,category,sort_order)")


@migration("0071-pgy-learner-audience")
def _pgy_learner_audience_71(conn, kind: str) -> None:
    """Persist the explicit PGY learner audience flag without granting RBAC."""
    boolean = "BOOLEAN" if kind == "postgres" else "INTEGER"
    default_false = "FALSE" if kind == "postgres" else "0"
    _add_columns(
        conn,
        kind,
        "user_accounts",
        {"pgy_learner": f"pgy_learner {boolean} NOT NULL DEFAULT {default_false}"},
    )


@migration("0072-course-bundle-idempotency")
def _course_bundle_idempotency_72(conn, kind: str) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS course_bundle_requests ("
        "username TEXT NOT NULL,workflow_id TEXT NOT NULL,request_hash TEXT NOT NULL,"
        "training_area TEXT NOT NULL,group_key TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'creating',"
        "course_id TEXT NOT NULL DEFAULT '',quiz_category_id TEXT NOT NULL DEFAULT '',"
        "result_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,"
        "PRIMARY KEY(username,workflow_id))"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_course_bundle_requests_status "
        "ON course_bundle_requests(status,updated_at)"
    )


@migration("0073-course-bundle-followups")
def _course_bundle_followups_73(conn, kind: str) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS course_bundle_followups ("
        "username TEXT NOT NULL,workflow_id TEXT NOT NULL,item_key TEXT NOT NULL,"
        "kind TEXT NOT NULL,request_hash TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'processing',"
        "response_status INTEGER NOT NULL DEFAULT 0,response_json TEXT NOT NULL DEFAULT '{}',"
        "created_at TEXT NOT NULL,updated_at TEXT NOT NULL,"
        "PRIMARY KEY(username,workflow_id,item_key))"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_course_bundle_followups_status "
        "ON course_bundle_followups(status,updated_at)"
    )


@migration("0074-assessment-list-indexes")
def _assessment_list_indexes_74(conn, kind: str) -> None:
    """Keep assessment list queries bounded on PostgreSQL and SQLite."""
    if _table_exists(conn, kind, "quiz_categories"):
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_quiz_categories_scope_list "
            "ON quiz_categories(group_key, training_area, active, sort_order, date_added)"
        )
    if _table_exists(conn, kind, "quiz_questions"):
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_quiz_questions_category_active "
            "ON quiz_questions(quiz_category_id, active)"
        )


def ensure_r2_free_budget_guard_67(base) -> None:
    """Compatibility maintenance helper for old callers and one-off repairs.

    Production startup applies ``0067-r2-free-budget-guard`` through the normal
    migration registry.  This helper remains intentionally explicit so a
    maintenance/test caller can re-run the idempotent DDL without reintroducing
    runtime schema mutation.
    """
    conn, kind = base._db_conn()
    try:
        _r2_free_budget_guard_67(conn, kind)
    finally:
        conn.close()


def _connect(base=None):
    return base._db_conn() if base is not None and hasattr(base, "_db_conn") else common_db.get_connection()


def ensure_registry(base=None) -> None:
    conn, kind = _connect(base)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
    finally:
        conn.close()


def apply_migrations(base=None) -> list[str]:
    ensure_registry(base)
    applied_now: list[str] = []
    conn, kind = _connect(base)
    ph = "%s" if kind == "postgres" else "?"
    try:
        rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
        applied = {str(dict(r).get("version", "")) for r in rows}
        for version, fn in MIGRATIONS:
            if version in applied:
                continue
            # Postgres/SQLite connectors in the legacy app use autocommit; migration
            # bodies therefore need to be idempotent. Each marker is inserted only
            # after the migration body succeeds.
            fn(conn, kind)
            conn.execute(
                f"INSERT INTO schema_migrations (version, applied_at) VALUES ({ph},{ph})",
                (version, utcnow()),
            )
            applied_now.append(version)
    finally:
        conn.close()
    return applied_now


def register_schema_migrations(owner):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_schema_migrations_registered"):
        return app
    applied = apply_migrations(owner if hasattr(owner, "_db_conn") else None)
    app.extensions["teacher_schema_migrations_registered"] = True
    app.extensions["teacher_schema_migrations_applied"] = applied
    return app
