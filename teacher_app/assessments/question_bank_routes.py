"""Canonical Question Bank 2.0 HTTP/RBAC routes."""
from __future__ import annotations

from flask import g, jsonify, request

from teacher_app.assessments import analytics as analytics_service
from teacher_app.assessments import blueprints as blueprint_service
from teacher_app.assessments import question_bank as bank_service
from teacher_app.common import scope_filter
from teacher_app.common.errors import ApiError

# Historical acceptance/tests import this symbol from the root module.  Keep a
# compatibility alias only; the implementation and runtime ownership are
# canonical in teacher_app.assessments.blueprints.
_draw = blueprint_service._draw


def _error(exc: ApiError):
    return jsonify({"error": exc.message, **(exc.extra or {})}), exc.status


def _app(owner):
    return getattr(owner, "app", owner)


def permitted(app, capability="question.manage", group=None):
    # ``scope_filter`` resolves quiz/category/question/blueprint group ownership
    # through canonical repositories.  Passing an explicit group keeps the same
    # fail-closed behavior for callers that already know the target scope.
    return scope_filter.scoped(app, capability, group)[1]


def register_question_bank(owner, *, runtime_question_runtime=None):
    app = _app(owner)
    if app.extensions.get("teacher_question_bank_68_registered"):
        return app

    # Factory still copies these long-lived legacy URLs before production
    # registration.  The canonical registrar replaces those endpoint views in
    # place (or adds them on a standalone app) without requiring a factory cut.
    from teacher_app.assessments.runtime_question_routes import register_runtime_question_routes

    # AI generation, question-image storage and progress reporting are still
    # owned by ``runtime_question_routes``.  Keep that dependency explicit so a
    # future factory cut can inject a narrow runtime without making this route
    # surface depend on a broad compatibility namespace.
    from teacher_app.assessments.question_runtime import runtime_from_owner

    register_runtime_question_routes(
        app,
        runtime=(
            runtime_question_runtime
            if runtime_question_runtime is not None
            else runtime_from_owner(owner)
        ),
    )

    @app.post("/api/question-bank/drafts")
    def create_draft():
        denied = permitted(app)
        if denied:
            return denied
        try:
            payload = bank_service.create_draft(request.get_json(silent=True) or {})
        except ApiError as exc:
            return _error(exc)
        return jsonify(payload), 201

    @app.get("/api/question-bank")
    def list_bank():
        denied = scope_filter.require_any_permission(app, "question.manage", "audit.read")
        if denied:
            return denied
        items = bank_service.list_questions(
            category_id=str(request.args.get("quizCategoryId") or "").strip(),
            status=str(request.args.get("status") or "").strip(),
        )
        return jsonify({"items": items})

    @app.patch("/api/question-bank/<question_id>")
    def update_bank_question(question_id):
        denied = permitted(app)
        if denied:
            return denied
        try:
            payload = bank_service.update_question(
                question_id,
                request.get_json(silent=True) or {},
            )
        except ApiError as exc:
            return _error(exc)
        return jsonify(payload)

    @app.delete("/api/question-bank/<question_id>")
    def delete_bank_question(question_id):
        denied = permitted(app)
        if denied:
            return denied
        return jsonify(bank_service.delete_question(question_id))

    @app.post("/api/question-bank/<question_id>/review")
    def review(question_id):
        denied = permitted(app, "question.review")
        if denied:
            return denied
        body = request.get_json(silent=True) or {}
        user = getattr(g, "teacher_user", None) or {}
        try:
            payload = bank_service.review_question(
                question_id,
                decision=str(body.get("decision") or ""),
                username=str(user.get("username") or ""),
            )
        except ApiError as exc:
            return _error(exc)
        return jsonify(payload)

    @app.post("/api/exam-blueprints")
    def blueprint():
        denied = permitted(app, "exam.manage")
        if denied:
            return denied
        user = getattr(g, "teacher_user", None) or {}
        try:
            payload = blueprint_service.create_blueprint(
                request.get_json(silent=True) or {},
                username=str(user.get("username") or ""),
            )
        except ApiError as exc:
            return _error(exc)
        return jsonify(payload), 201

    @app.get("/api/questions/<question_id>/analytics")
    def analytics(question_id):
        denied = scope_filter.require_any_permission(app, "question.manage", "audit.read")
        if denied:
            return denied
        return jsonify(analytics_service.get_question_analytics(question_id))

    @app.post("/api/exam-blueprints/<blueprint_id>/publish")
    def publish_blueprint(blueprint_id):
        denied = permitted(app, "exam.publish")
        if denied:
            return denied
        try:
            payload, status = blueprint_service.publish_blueprint(blueprint_id)
        except ApiError as exc:
            return _error(exc)
        return jsonify(payload), status

    app.extensions["teacher_question_bank_68_registered"] = True
    return app
