"""Teacher schema migration registry.

This establishes a migration baseline without rewriting legacy init_db logic.
Future migrations can be appended to MIGRATIONS and are applied exactly once.
"""
from __future__ import annotations

import datetime as dt
import json
from typing import Any, Callable

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
    """6.4 baseline marker; legacy tables are already created by app.py."""
    return None


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
    _add_columns(
        conn,
        kind,
        "pgy_assignments",
        {
            "sign_mode": "sign_mode TEXT NOT NULL DEFAULT 'legacy'",
            "first_signature": "first_signature TEXT NOT NULL DEFAULT '{}'",
            "second_signature": "second_signature TEXT NOT NULL DEFAULT '{}'",
        },
    )


def ensure_registry(base) -> None:
    conn, kind = base._db_conn()
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


def apply_migrations(base) -> list[str]:
    ensure_registry(base)
    applied_now: list[str] = []
    conn, kind = base._db_conn()
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


def register_schema_migrations(base):
    app = base.app
    if app.extensions.get("teacher_schema_migrations_registered"):
        return app
    applied = apply_migrations(base)
    app.extensions["teacher_schema_migrations_registered"] = True
    app.extensions["teacher_schema_migrations_applied"] = applied
    return app
