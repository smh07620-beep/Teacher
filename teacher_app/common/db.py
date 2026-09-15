"""Unified database helpers wrapping the 6.4 PostgreSQL / SQLite split.

``app._db_conn()`` is intentionally left in place. New code should call these
helpers; legacy modules keep using ``_db_conn`` until later milestones.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator, Optional, Sequence, Tuple

from teacher_app.config import database_url, sqlite_path

ConnKind = str
ConnectionPair = Tuple[Any, ConnKind]


def get_connection() -> ConnectionPair:
    """Match ``app._db_conn``: DATABASE_URL forces PostgreSQL, else SQLite."""
    url = database_url()
    if url:
        import psycopg
        from psycopg.rows import dict_row

        conn = psycopg.connect(url, row_factory=dict_row, connect_timeout=10)
        conn.autocommit = True
        return conn, "postgres"

    path = sqlite_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.isolation_level = None
    return conn, "sqlite"


def placeholder(kind: Optional[str] = None) -> str:
    if kind is None:
        kind = "postgres" if database_url() else "sqlite"
    return "%s" if kind == "postgres" else "?"


def _as_mapping(row: Any) -> Optional[dict]:
    if row is None:
        return None
    return dict(row)


def fetch_one(conn, sql: str, params: Sequence[Any] = ()) -> Optional[dict]:
    return _as_mapping(conn.execute(sql, params).fetchone())


def fetch_all(conn, sql: str, params: Sequence[Any] = ()) -> list[dict]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def execute(conn, sql: str, params: Sequence[Any] = ()):
    return conn.execute(sql, params)


@contextmanager
def transaction() -> Iterator[ConnectionPair]:
    conn, kind = get_connection()
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
