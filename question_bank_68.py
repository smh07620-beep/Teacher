"""Question Bank 2.0 HTTP adapter plus deferred analytics runtime."""
from __future__ import annotations

from collections import Counter

from flask import jsonify, request

from teacher_app.assessments import blueprints as blueprint_service
from teacher_app.assessments import question_bank as bank_service
from teacher_app.common.errors import ApiError

# Historical acceptance/tests import this symbol from the root module.  Keep a
# compatibility alias only; the implementation and runtime ownership are
# canonical in teacher_app.assessments.blueprints.
_draw = blueprint_service._draw


def _error(exc: ApiError):
    return jsonify({"error": exc.message, **(exc.extra or {})}), exc.status


def permitted(base, capability="question.manage", group=None):
    if not hasattr(base, "require_scoped_permission"):
        return base.require_admin()
    # Question rows use the existing quiz-category assignment for scope.  An
    # absent category is deliberately not widened for a teacher/group leader.
    if group is None:
        body = request.get_json(silent=True) or {}
        category = str(
            request.args.get("quizCategoryId")
            or body.get("quizCategoryId")
            or ""
        ).strip()
        if category:
            quiz = base.get_quiz_category(category)
            group = (quiz or {}).get("group")
    return base.require_scoped_permission(capability, group)


def register_question_bank(base):
    app = base.app
    if app.extensions.get("teacher_question_bank_68_registered"):
        return app

    @app.post("/api/question-bank/drafts")
    def create_draft():
        denied = permitted(base)
        if denied:
            return denied
        try:
            payload = bank_service.create_draft(request.get_json(silent=True) or {})
        except ApiError as exc:
            return _error(exc)
        return jsonify(payload), 201

    @app.get("/api/question-bank")
    def list_bank():
        denied = (
            base.require_any_permission("question.manage", "audit.read")
            if hasattr(base, "require_any_permission")
            else base.require_admin()
        )
        if denied:
            return denied
        items = bank_service.list_questions(
            category_id=str(request.args.get("quizCategoryId") or "").strip(),
            status=str(request.args.get("status") or "").strip(),
        )
        return jsonify({"items": items})

    @app.patch("/api/question-bank/<question_id>")
    def update_bank_question(question_id):
        denied = permitted(base)
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
        denied = permitted(base)
        if denied:
            return denied
        return jsonify(bank_service.delete_question(question_id))

    @app.post("/api/question-bank/<question_id>/review")
    def review(question_id):
        denied = permitted(base, "question.review")
        if denied:
            return denied
        body = request.get_json(silent=True) or {}
        user = base._current_user() or {}
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
        denied = permitted(base, "exam.manage")
        if denied:
            return denied
        user = base._current_user() or {}
        try:
            payload = blueprint_service.create_blueprint(
                request.get_json(silent=True) or {},
                username=str(user.get("username") or ""),
            )
        except ApiError as exc:
            return _error(exc)
        return jsonify(payload), 201

    # Item analytics remains the final bounded Question Bank runtime owner.
    @app.get("/api/questions/<question_id>/analytics")
    def analytics(question_id):
        denied = (
            base.require_any_permission("question.manage", "audit.read")
            if hasattr(base, "require_any_permission")
            else base.require_admin()
        )
        if denied:
            return denied
        conn, kind = base._db_conn()
        ph = "%s" if kind == "postgres" else "?"
        try:
            rows = conn.execute(
                f"SELECT selected_option,is_correct FROM question_attempt_analytics WHERE question_id={ph}",
                (question_id,),
            ).fetchall()
        finally:
            conn.close()
        attempt_count = len(rows)
        if attempt_count < 10:
            return jsonify({
                "attemptCount": attempt_count,
                "sufficientData": False,
                "message": "資料不足",
            })
        values = [dict(row) for row in rows]
        counts = dict(Counter(row["selected_option"] for row in values))
        conn, kind = base._db_conn()
        ph = "%s" if kind == "postgres" else "?"
        try:
            question = conn.execute(
                f"SELECT correct FROM quiz_questions WHERE id={ph}",
                (question_id,),
            ).fetchone()
        finally:
            conn.close()
        correct = str(dict(question).get("correct", "") if question else "")
        return jsonify({
            "attemptCount": attempt_count,
            "sufficientData": True,
            "correctRate": round(
                sum(bool(row["is_correct"]) for row in values) / attempt_count,
                3,
            ),
            "optionSelectionCounts": counts,
            "distractorDistribution": {
                key: value for key, value in counts.items() if str(key) != correct
            },
        })

    @app.post("/api/exam-blueprints/<blueprint_id>/publish")
    def publish_blueprint(blueprint_id):
        denied = permitted(base, "exam.publish")
        if denied:
            return denied
        try:
            payload, status = blueprint_service.publish_blueprint(blueprint_id)
        except ApiError as exc:
            return _error(exc)
        return jsonify(payload), status

    app.extensions["teacher_question_bank_68_registered"] = True
    return app
