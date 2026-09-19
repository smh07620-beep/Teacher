"""Blueprint routes and the 6.4 production route adapter for exams."""

from __future__ import annotations

from flask import g, jsonify, request

from teacher_app.common.auth import has_role
from teacher_app.common.errors import ApiError
from teacher_app.exams import bp
from teacher_app.exams import grading
from teacher_app.exams import repository as repo
from teacher_app.exams import service


def _legacy_error(exc: ApiError):
    body = {"error": exc.message}
    body.update(exc.extra)
    return jsonify(body), exc.status


def _call(handler, *args):
    try:
        return handler(*args)
    except ApiError as exc:
        return _legacy_error(exc)


def _blueprint_user():
    return getattr(g, "exam_user", None)


@bp.errorhandler(ApiError)
def exam_error(exc: ApiError):
    body = {"ok": False, "error": exc.message, "errorDetail": {"code": exc.code, "message": exc.message}}
    body.update(exc.extra)
    return jsonify(body), exc.status


@bp.post("/api/exam-attempts")
def exam_attempt_start():
    return jsonify(service.start_attempt(_blueprint_user(), request.get_json(silent=True) or {})), 201


@bp.get("/api/exam-attempts/<attempt_id>")
def exam_attempt_resume(attempt_id):
    return jsonify(service.resume_attempt(_blueprint_user(), attempt_id))


@bp.post("/api/exam-attempts/<attempt_id>/submit")
def exam_attempt_submit(attempt_id):
    return jsonify(service.submit_attempt(_blueprint_user(), attempt_id, request.get_json(silent=True) or {}))


def register_legacy_exam_routes(base):
    """Mount modular exam behavior on the unchanged ``pgy_app:app`` URLs."""
    app = base.app
    if app.extensions.get("exam_integrity_registered"):
        return app
    repo.init_schema(base)
    app.extensions["exam_integrity_registered"] = True

    @app.before_request
    def reject_legacy_client_scoring():
        if request.path == "/api/records" and request.method == "POST":
            user = base._current_user()
            role = base.normalize_role((user or {}).get("role", "student"))
            if user and role not in {"education_admin", "system_admin"}:
                return jsonify({"error": "此版本已改由伺服器計分，請重新整理考核頁後再提交。",
                                "secureExamRequired": True}), 409
        return None

    @app.after_request
    def remove_answer_keys_from_learner_question_api(response):
        try:
            if request.method != "GET" or request.path not in {"/api/quiz-questions", "/api/quiz-questions/random"}:
                return response
            user = base._current_user()
            role = base.normalize_role((user or {}).get("role", "student"))
            if user and role in {"education_admin", "system_admin"}:
                return response
            if response.status_code != 200 or not str(response.content_type or "").startswith("application/json"):
                return response
            data = response.get_json(silent=True)
            if isinstance(data, list):
                response.set_data(repo.json_dump([grading.sanitize_question(q) for q in data if isinstance(q, dict)]))
                response.content_type = "application/json; charset=utf-8"
        except Exception:
            return response
        return response

    @app.post("/api/exam-attempts")
    def exam_attempt_start():
        result = _call(service.start_attempt, base, base._current_user(), request.get_json(silent=True) or {})
        if isinstance(result, tuple):
            return result
        return jsonify(result), 201

    @app.get("/api/exam-attempts/<attempt_id>")
    def exam_attempt_resume(attempt_id):
        result = _call(service.resume_attempt, base, base._current_user(), attempt_id)
        return result if isinstance(result, tuple) else jsonify(result)

    @app.post("/api/exam-attempts/<attempt_id>/submit")
    def exam_attempt_submit(attempt_id):
        result = _call(service.submit_attempt, base, base._current_user(), attempt_id, request.get_json(silent=True) or {})
        return result if isinstance(result, tuple) else jsonify(result)

    return app


def register_exam_integrity_guards(owner):
    """Register only the legacy-record and learner-answer safety hooks.

    The ``teacher_exams`` blueprint owns the secure attempt URLs in the
    application factory.  This registration keeps the two compatibility
    guards that still protect legacy record/question endpoints.
    """
    app = getattr(owner, "app", owner)
    if app.extensions.get("exam_integrity_guards_registered"):
        return app
    repo.init_schema()
    app.extensions["exam_integrity_guards_registered"] = True

    @app.before_request
    def reject_legacy_client_scoring_guard():
        if request.path == "/api/records" and request.method == "POST":
            user = getattr(g, "teacher_user", None)
            if user and not (
                has_role(user, "education_admin") or has_role(user, "system_admin")
            ):
                return jsonify({
                    "error": "此版本已改由伺服器計分，請重新整理考核頁後再提交。",
                    "secureExamRequired": True,
                }), 409
        return None

    @app.after_request
    def remove_answer_keys_from_learner_question_api_guard(response):
        try:
            if request.method != "GET" or request.path not in {"/api/quiz-questions", "/api/quiz-questions/random"}:
                return response
            user = getattr(g, "teacher_user", None)
            if user and (
                has_role(user, "education_admin") or has_role(user, "system_admin")
            ):
                return response
            if response.status_code != 200 or not str(response.content_type or "").startswith("application/json"):
                return response
            data = response.get_json(silent=True)
            if isinstance(data, list):
                response.set_data(repo.json_dump([
                    grading.sanitize_question(question)
                    for question in data
                    if isinstance(question, dict)
                ]))
                response.content_type = "application/json; charset=utf-8"
        except Exception:
            return response
        return response

    return app
