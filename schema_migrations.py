"""Teacher 6.5 lightweight schema migration registry.

This establishes a migration baseline without rewriting legacy init_db logic.
Future migrations can be appended to MIGRATIONS and are applied exactly once.
"""
from __future__ import annotations

import datetime as dt
from typing import Callable, Iterable, Tuple

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
