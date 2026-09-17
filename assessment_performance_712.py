"""Teacher 7.12 assessment-list latency hardening.

This module keeps the existing auth and assessment owners intact while removing
avoidable repeated work around the Render -> Supabase round trip:

* cache ``base._current_user()`` only for the lifetime of one Flask request, so
  RBAC guards and after-request scope filters do not re-query the same account;
* add the indexes used by the assessment list/count query;
* emit coarse slow-path timings without logging usernames, SQL parameters or
  credentials.
"""
from __future__ import annotations

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


def register_assessment_performance_712(base):
    app = base.app
    if app.extensions.get("teacher_assessment_performance_712_registered"):
        return app

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
        if elapsed_ms >= 1000:
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
        if elapsed_ms >= 1000:
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
