"""Canonical Question Bank 2.0 HTTP/RBAC routes."""
from __future__ import annotations

import json

from flask import g, jsonify, request

from teacher_app.assessments import analytics as analytics_service
from teacher_app.assessments import blueprints as blueprint_service
from teacher_app.assessments import question_bank as bank_service
from teacher_app.assessments import repository
from teacher_app.common import audit, scope_filter
from teacher_app.common.auth import has_permission
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

    def actor():
        return getattr(g, "teacher_user", None) or {}

    def snapshot(row):
        if not row:
            return {}
        item = bank_service.question_payload(row)
        return {
            "id": str(item.get("id") or ""),
            "quizCategoryId": str(item.get("quizCategoryId") or ""),
            "questionType": str(item.get("questionType") or ""),
            "status": str(item.get("status") or ""),
            "origin": str(item.get("origin") or ""),
            "active": bool(item.get("active", True)),
            "reviewedBy": str(item.get("reviewedBy") or ""),
            "reviewedAt": str(item.get("reviewedAt") or ""),
        }

    def category_for_scope(category_id):
        category_id = str(category_id or "")
        if not category_id:
            return None
        try:
            category = repository.get_category_full(category_id)
        except Exception:
            # Isolated legacy fixtures may register this adapter against a
            # deliberately minimal question-only schema. Production factory
            # composition owns quiz_categories, so only a non-app compatibility
            # owner may fall back to its historical category resolver.
            if owner is app:
                raise
            resolver = getattr(owner, "get_quiz_category", None)
            if not callable(resolver):
                raise
            category = resolver(category_id)
        return category

    def question_group(row):
        category_id = str((row or {}).get("quiz_category_id") or (row or {}).get("quizCategoryId") or "")
        category = category_for_scope(category_id)
        return str((category or {}).get("group") or "")

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
        before = repository.get_bank_question(question_id)
        payload = bank_service.delete_question(question_id)
        if payload.get("ok"):
            audit.record_event(
                actor=actor(),
                action="question.delete",
                target_type="question",
                target_id=question_id,
                group=question_group(before),
                before=snapshot(before),
                detail={"source": "question_bank"},
            )
        return jsonify(payload)

    @app.post("/api/question-bank/<question_id>/review")
    def review(question_id):
        denied = permitted(app, "question.review")
        if denied:
            return denied
        body = request.get_json(silent=True) or {}
        user = getattr(g, "teacher_user", None) or {}
        before = repository.get_bank_question(question_id)
        try:
            payload = bank_service.review_question(
                question_id,
                decision=str(body.get("decision") or ""),
                username=str(user.get("username") or ""),
            )
        except ApiError as exc:
            return _error(exc)
        after = repository.get_bank_question(question_id)
        if payload.get("ok"):
            audit.record_event(
                actor=actor(),
                action="question.review",
                target_type="question",
                target_id=question_id,
                group=question_group(after or before),
                before=snapshot(before),
                after=snapshot(after),
                detail={"decision": str(body.get("decision") or "")[:20]},
            )
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
        raw_version = request.args.get("version")
        try:
            version = max(1, int(raw_version)) if raw_version not in (None, "") else None
        except (TypeError, ValueError):
            return jsonify({"error": "version 格式錯誤"}), 400
        return jsonify(analytics_service.get_question_analytics(question_id, version=version))

    @app.get("/api/question-bank/<question_id>/versions")
    def question_versions(question_id):
        denied = scope_filter.require_any_permission(app, "question.manage", "audit.read")
        if denied:
            return denied
        versions = repository.list_question_versions(question_id)
        user = actor()
        if versions and has_permission(user, "question.manage"):
            denied = scope_filter.scoped(
                app,
                "question.manage",
                str(versions[0].get("group_key") or ""),
            )[1]
            if denied:
                return denied
        return jsonify({
            "questionId": question_id,
            "versions": [
                {
                    "version": int(item.get("version") or 1),
                    "questionHash": str(item.get("question_hash") or ""),
                    "quizCategoryId": str(item.get("quiz_category_id") or ""),
                    "group": str(item.get("group_key") or ""),
                    "createdAt": str(item.get("created_at") or ""),
                    "createdBy": str(item.get("created_by") or ""),
                    "changeReason": str(item.get("change_reason") or ""),
                    "snapshot": item.get("snapshot") or {},
                }
                for item in versions
            ],
        })

    @app.post("/api/exam-blueprints/<blueprint_id>/publish")
    def publish_blueprint(blueprint_id):
        denied = permitted(app, "exam.publish")
        if denied:
            return denied
        blueprint_row = repository.get_blueprint(blueprint_id)
        category_id = str((blueprint_row or {}).get("quiz_category_id") or "")
        category = category_for_scope(category_id)
        try:
            payload, status = blueprint_service.publish_blueprint(blueprint_id)
        except ApiError as exc:
            return _error(exc)
        snapshot_row = repository.get_blueprint_snapshot(blueprint_id) or {}
        try:
            snapshot_questions = json.loads(snapshot_row.get("questions") or "[]")
        except (TypeError, ValueError, json.JSONDecodeError):
            snapshot_questions = []
        question_ids = [
            str(item.get("id") or "")
            for item in snapshot_questions
            if isinstance(item, dict) and item.get("id")
        ]
        audit.record_event(
            actor=actor(),
            action="question.publish",
            target_type="question_snapshot",
            target_id=str(payload.get("id") or blueprint_id),
            group=str((category or {}).get("group") or ""),
            scope={
                "quizCategoryId": category_id,
                "area": str((category or {}).get("area") or ""),
            },
            detail={
                "blueprintId": blueprint_id,
                "questionIds": question_ids,
                "questionCount": len(question_ids),
                "immutable": bool(payload.get("immutable", True)),
            },
        )
        return jsonify(payload), status

    app.extensions["teacher_question_bank_68_registered"] = True
    return app
