"""Teacher 7.12 assessment-list latency hardening.

The dominant production cost here is the Render -> Supabase connection setup,
not five rows of SQL.  Keep canonical auth/assessment ownership intact while
removing avoidable round trips:

* use a small per-Gunicorn-worker PostgreSQL connection pool so ordinary API
  requests do not perform a new TLS/database handshake for every query;
* cache ``base._current_user()`` only for the lifetime of one Flask request, so
  RBAC guards and after-request scope filters do not re-query the same account;
* add the indexes used by the assessment list/count query;
* emit coarse slow-path timings without logging usernames, SQL parameters or
  credentials.

The auth result is deliberately NOT cached across requests: account activity,
roles and ``session_version`` must still be validated on every HTTP request.
"""
from __future__ import annotations

import os
import time

from flask import g, has_request_context

from schema_migrations import _table_exists, migration


@migration("0074-assessment-list-indexes")
def _assessment_list_indexes_712(conn, kind: str) -> None:
    """Indexes for the two queries behind the assessment list endpoint."""
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


class _PooledConnectionHandle:
    """Return a psycopg connection to its pool when legacy code calls close()."""

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
            # A legacy caller may leave an explicit transaction open after an
            # exception.  Roll it back before another request borrows it.
            from psycopg.pq import TransactionStatus

            if conn.info.transaction_status not in {
                TransactionStatus.IDLE,
                TransactionStatus.UNKNOWN,
            }:
                conn.rollback()
        except Exception:
            # psycopg_pool discards broken connections when they are returned.
            pass
        pool.putconn(conn)


def _install_postgres_pool(base, app):
    """Replace only the legacy PostgreSQL connection seam with a bounded pool."""
    database_url = str(getattr(base, "DATABASE_URL", "") or "").strip()
    if not database_url:
        return None
    if app.extensions.get("teacher_db_pool_712") is not None:
        return app.extensions["teacher_db_pool_712"]

    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    try:
        thread_default = int(os.environ.get("GUNICORN_THREADS", "4") or 4)
    except (TypeError, ValueError):
        thread_default = 4
    try:
        max_size = int(os.environ.get("DB_POOL_MAX_SIZE", str(thread_default)) or thread_default)
    except (TypeError, ValueError):
        max_size = thread_default
    max_size = max(2, min(8, max_size))
    try:
        min_size = int(os.environ.get("DB_POOL_MIN_SIZE", "1") or 1)
    except (TypeError, ValueError):
        min_size = 1
    min_size = max(1, min(max_size, min_size))
    try:
        checkout_timeout = float(os.environ.get("DB_POOL_TIMEOUT_SECONDS", "5") or 5)
    except (TypeError, ValueError):
        checkout_timeout = 5.0
    checkout_timeout = max(1.0, min(15.0, checkout_timeout))

    # min_size=1 pre-warms one connection in the worker.  At the current
    # 1-worker x 4-thread Render shape, max_size=4 is enough to stop connection
    # setup from dominating every request without opening an excessive number
    # of Supabase sessions.
    pool = ConnectionPool(
        conninfo=database_url,
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
    original_db_conn = base._db_conn

    def pooled_db_conn():
        started = time.perf_counter()
        try:
            conn = pool.getconn(timeout=checkout_timeout)
        except Exception:
            # Do not stampede Supabase with direct fallback connections when the
            # bounded pool is exhausted; surface the real DB availability issue.
            app.logger.exception("teacher712 database pool checkout failed")
            raise
        elapsed_ms = (time.perf_counter() - started) * 1000
        if elapsed_ms >= 250:
            app.logger.warning("teacher712 slow db checkout: %.0fms", elapsed_ms)
        return _PooledConnectionHandle(pool, conn), "postgres"

    # Keep the original only for diagnostics/tests; live request code uses the
    # same legacy seam and therefore automatically benefits from pooling.
    app.extensions["teacher_db_conn_original_712"] = original_db_conn
    app.extensions["teacher_db_pool_712"] = pool
    base._db_conn = pooled_db_conn
    app.logger.info(
        "teacher712 PostgreSQL pool enabled min=%d max=%d checkout_timeout=%.1fs",
        min_size,
        max_size,
        checkout_timeout,
    )
    return pool


def register_assessment_performance_712(base):
    app = base.app
    if app.extensions.get("teacher_assessment_performance_712_registered"):
        return app

    # Schema migrations run before this registration, so installing the pool
    # here cannot change migration transaction semantics.
    _install_postgres_pool(base, app)

    original_current_user = base._current_user
    original_list = base.list_quiz_categories_with_counts

    def request_cached_current_user():
        # The RBAC legacy adapter can consult the current user both before and
        # after a list endpoint.  The canonical auth helper validates account
        # activity/session_version from the DB; repeat that validation only once
        # per HTTP request, never across requests.
        if not has_request_context():
            return original_current_user()
        cache_attr = "_teacher712_current_user"
        if hasattr(g, cache_attr):
            return getattr(g, cache_attr)
        started = time.perf_counter()
        user = original_current_user()
        elapsed_ms = (time.perf_counter() - started) * 1000
        setattr(g, cache_attr, user)
        if elapsed_ms >= 250:
            app.logger.warning(
                "teacher712 slow auth lookup: %.0fms endpoint=%s",
                elapsed_ms,
                getattr(__import__("flask").request, "endpoint", "") or "unknown",
            )
        return user

    def timed_category_list(*args, **kwargs):
        started = time.perf_counter()
        result = original_list(*args, **kwargs)
        elapsed_ms = (time.perf_counter() - started) * 1000
        if elapsed_ms >= 250:
            app.logger.warning(
                "teacher712 slow assessment list query: %.0fms rows=%d",
                elapsed_ms,
                len(result or []),
            )
        return result

    base._current_user = request_cached_current_user
    base.list_quiz_categories_with_counts = timed_category_list
    app.extensions["teacher_assessment_performance_712_registered"] = True
    return app
