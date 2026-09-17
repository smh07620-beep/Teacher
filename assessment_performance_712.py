"""Teacher 7.12 assessment-list latency hardening.

Connection setup is handled centrally by ``teacher_app.common.db`` so both
legacy and canonical Teacher modules share the same bounded PostgreSQL pool.
This module keeps the request-scoped auth cache, assessment indexes and
slow-path diagnostics close to the feature that exposed the latency.
"""
from __future__ import annotations

import time

from flask import g, has_request_context

from schema_migrations import _table_exists, migration
from teacher_app.common import db as common_db


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


def _install_shared_connection_seam(base, app):
    """Make legacy ``app._db_conn`` use the same pool as canonical modules."""
    database_url = str(getattr(base, "DATABASE_URL", "") or "").strip()
    if not database_url:
        return None
    if app.extensions.get("teacher_db_pool_712") is not None:
        return app.extensions["teacher_db_pool_712"]

    pool = common_db.ensure_postgres_pool()
    app.extensions["teacher_db_conn_original_712"] = base._db_conn
    app.extensions["teacher_db_pool_712"] = pool
    base._db_conn = common_db.get_connection
    return pool


def register_assessment_performance_712(base):
    app = base.app
    if app.extensions.get("teacher_assessment_performance_712_registered"):
        return app

    # Schema migrations run before this registration.  From this point forward
    # both legacy app.py code and canonical teacher_app modules reuse the same
    # process-local PostgreSQL pool.
    _install_shared_connection_seam(base, app)

    original_current_user = base._current_user
    original_list = base.list_quiz_categories_with_counts

    def request_cached_current_user():
        # The RBAC legacy adapter can consult the current user both before and
        # after a list endpoint.  Validate account activity/session_version once
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
