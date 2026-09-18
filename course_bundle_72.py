"""Course Wizard bundle HTTP compatibility adapter.

Retry-safe course/exam bundle creation lives in ``teacher_app.courses.bundle``.
This root module preserves the public URL, capability gates, response projection
and the historical 0072 migration registration order.
"""
from __future__ import annotations

from flask import jsonify, request

from schema_migrations import MIGRATIONS, migration
from teacher_app.common.errors import ApiError
from teacher_app.courses import bundle as bundle_service


MIGRATION_ID = bundle_service.MIGRATION_ID
WORKFLOW_RE = bundle_service.WORKFLOW_RE
EXAM_MODES = bundle_service.EXAM_MODES


def _course_bundle_idempotency_72(conn, kind: str) -> None:
    """Historical startup migration hook retained until migration convergence."""
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


if not any(version == MIGRATION_ID for version, _fn in MIGRATIONS):
    migration(MIGRATION_ID)(_course_bundle_idempotency_72)


def _hydrate(base, result: dict) -> dict:
    """Preserve the legacy material/course response projection only."""
    output = dict(result or {})
    course = output.get("course") or {}
    category = output.get("quizCategory") or None
    try:
        current = base.get_course(str(course.get("id") or "")) if course else None
        if current:
            output["course"] = current
    except Exception:
        pass
    if category:
        try:
            current = base.get_quiz_category(str(category.get("id") or ""))
            if current:
                output["quizCategory"] = current
        except Exception:
            pass
    return output


def _error(exc: ApiError):
    body = {"error": exc.message}
    if exc.code in {"IDEMPOTENCY_KEY_REUSED", "WORKFLOW_IN_PROGRESS"}:
        body["code"] = exc.code
    if exc.extra.get("loginRequired"):
        body["loginRequired"] = True
    return jsonify(body), exc.status


def register_course_bundle_72(base):
    app = base.app
    if app.extensions.get("teacher_course_bundle_72_registered"):
        return app

    def create_course_bundle():
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"error": "請提供有效的建立資料。"}), 400

        # Capability/RBAC remains at the existing HTTP boundary.
        denied = base.require_permission("course.manage")
        if denied:
            return denied
        exam_mode = str(data.get("examMode") or "later").strip().lower()
        if exam_mode != "later":
            denied = base.require_permission("question.manage")
            if denied:
                return denied

        try:
            result, status_code = bundle_service.create_bundle(
                base._current_user(),
                data,
            )
        except ApiError as exc:
            return _error(exc)
        except Exception:
            return jsonify({
                "error": "建立課程流程失敗，未完成的資料已回復；可使用相同流程識別碼重試。"
            }), 500

        return jsonify(_hydrate(base, result)), status_code

    app.add_url_rule(
        "/api/course-bundles",
        endpoint="course_bundle_create_72",
        view_func=create_course_bundle,
        methods=["POST"],
    )
    app.extensions["teacher_course_bundle_72_registered"] = True
    return app
