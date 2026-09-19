"""Unified database helpers wrapping the PostgreSQL / SQLite split.

PostgreSQL connections are process-local and pooled.  This is important on the
Render -> Supabase path where opening a fresh TLS/database session can cost more
than the tiny queries Teacher normally executes.  Existing callers still own
their connection lifetime and may keep calling ``close()``; pooled handles turn
that into a return-to-pool operation.
"""

from __future__ import annotations

import atexit
import logging
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator, Optional, Sequence, Tuple

from teacher_app.config import database_url, sqlite_path

ConnKind = str
ConnectionPair = Tuple[Any, ConnKind]
_LOG = logging.getLogger(__name__)
_POOL_LOCK = threading.Lock()
_POSTGRES_POOL = None
_POSTGRES_POOL_URL = ""
_SLOW_CHECKOUT_MS = 250.0


def _env_int(name: str, default: int, lower: int, upper: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)) or default)
    except (TypeError, ValueError):
        value = default
    return max(lower, min(upper, value))


def _env_float(name: str, default: float, lower: float, upper: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)) or default)
    except (TypeError, ValueError):
        value = default
    return max(lower, min(upper, value))


class _PooledConnectionHandle:
    """Proxy a psycopg connection and return it to the pool on ``close()``."""

    def __init__(self, pool, conn):
        object.__setattr__(self, "_pool", pool)
        object.__setattr__(self, "_conn", conn)
        object.__setattr__(self, "_returned", False)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_conn"), name)

    def __setattr__(self, name, value):
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        setattr(object.__getattribute__(self, "_conn"), name, value)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        conn = object.__getattribute__(self, "_conn")
        try:
            if exc_type is not None:
                conn.rollback()
            elif not conn.autocommit:
                conn.commit()
        finally:
            self.close()
        return False

    def close(self):
        if object.__getattribute__(self, "_returned"):
            return
        object.__setattr__(self, "_returned", True)
        pool = object.__getattribute__(self, "_pool")
        conn = object.__getattribute__(self, "_conn")
        try:
            from psycopg.pq import TransactionStatus

            if conn.info.transaction_status not in {
                TransactionStatus.IDLE,
                TransactionStatus.UNKNOWN,
            }:
                conn.rollback()
        except Exception:
            # psycopg_pool validates/discards broken connections on return.
            pass
        pool.putconn(conn)


def _new_postgres_pool(url: str):
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    thread_default = _env_int("GUNICORN_THREADS", 4, 1, 16)
    max_size = _env_int("DB_POOL_MAX_SIZE", thread_default, 2, 8)
    min_size = _env_int("DB_POOL_MIN_SIZE", 1, 1, max_size)
    checkout_timeout = _env_float("DB_POOL_TIMEOUT_SECONDS", 5.0, 1.0, 15.0)

    pool = ConnectionPool(
        conninfo=url,
        min_size=min_size,
        max_size=max_size,
        timeout=checkout_timeout,
        max_idle=300,
        max_lifetime=1800,
        reconnect_timeout=10,
        kwargs={
            "row_factory": dict_row,
            "autocommit": True,
            "connect_timeout": 10,
        },
        name="teacher-web-db",
        open=True,
    )
    _LOG.info(
        "teacher712 PostgreSQL pool enabled min=%d max=%d checkout_timeout=%.1fs",
        min_size,
        max_size,
        checkout_timeout,
    )
    return pool


def ensure_postgres_pool():
    """Return the process-local pool, creating it lazily when DATABASE_URL exists."""
    global _POSTGRES_POOL, _POSTGRES_POOL_URL
    url = database_url()
    if not url:
        return None
    if _POSTGRES_POOL is not None and _POSTGRES_POOL_URL == url:
        return _POSTGRES_POOL
    with _POOL_LOCK:
        if _POSTGRES_POOL is not None and _POSTGRES_POOL_URL == url:
            return _POSTGRES_POOL
        old = _POSTGRES_POOL
        _POSTGRES_POOL = _new_postgres_pool(url)
        _POSTGRES_POOL_URL = url
        if old is not None:
            try:
                old.close()
            except Exception:
                pass
        return _POSTGRES_POOL


def close_postgres_pool() -> None:
    global _POSTGRES_POOL, _POSTGRES_POOL_URL
    with _POOL_LOCK:
        pool = _POSTGRES_POOL
        _POSTGRES_POOL = None
        _POSTGRES_POOL_URL = ""
    if pool is not None:
        try:
            pool.close()
        except Exception:
            pass


atexit.register(close_postgres_pool)


def get_connection() -> ConnectionPair:
    """DATABASE_URL forces pooled PostgreSQL; local development uses SQLite."""
    url = database_url()
    if url:
        pool = ensure_postgres_pool()
        checkout_timeout = _env_float("DB_POOL_TIMEOUT_SECONDS", 5.0, 1.0, 15.0)
        started = time.perf_counter()
        try:
            conn = pool.getconn(timeout=checkout_timeout)
        except Exception:
            _LOG.exception("teacher712 database pool checkout failed")
            raise
        elapsed_ms = (time.perf_counter() - started) * 1000
        if elapsed_ms >= _SLOW_CHECKOUT_MS:
            _LOG.warning("teacher712 slow db checkout: %.0fms", elapsed_ms)
        return _PooledConnectionHandle(pool, conn), "postgres"

    path = sqlite_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.isolation_level = None
    return conn, "sqlite"


@contextmanager
def read_connection() -> Iterator[ConnectionPair]:
    """Yield one read connection and always return/close it at scope exit.

    Repositories use this helper for read-only work so PostgreSQL always checks
    out from the process-local pool while SQLite keeps the same explicit close
    semantics. Write units of work must use transaction() instead.
    """
    conn, kind = get_connection()
    try:
        yield conn, kind
    finally:
        conn.close()


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
