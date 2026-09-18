"""HTTP adapter for Teacher 7.1 Training Command Center."""

from __future__ import annotations

from flask import g, jsonify

from teacher_app.command_center import analytics, audience, competency, service
from teacher_app.common.errors import ApiError


def _error(exc: ApiError):
    body = {"error": exc.message}
    body.update(exc.extra)
    return jsonify(body), exc.status


def _online_matrix(profile):
    return {
        "audience": "online",
        "pgyLearner": False,
        "scope": {"kind": "self", "roles": profile.get("roles", []), "group": profile.get("group", "")},
        "assessmentTypes": [],
        "summary": {
            "learners": 0,
            "assignments": 0,
            "assignmentsCompleted": 0,
            "assignmentsOverdue": 0,
            "assignmentCompletionPercent": 0.0,
            "assessments": 0,
            "averageAssessmentScore": None,
        },
        "learners": [],
        "interpretation": "not_pgy_learner",
    }


def _suppress_pgy_analytics(data):
    result = dict(data or {})
    result["audience"] = "online"
    result["pgyLearner"] = False
    summary = dict(result.get("summary") or {})
    for key in (
        "pgyAssignments",
        "pgyCompletedAssignments",
        "pgyCompletionRate",
        "averagePgyAssessmentScore",
    ):
        summary.pop(key, None)
    result["summary"] = summary
    learners = []
    for raw in result.get("learners") or []:
        row = dict(raw)
        row.pop("pgy", None)
        row["audience"] = "online"
        row["pgyLearner"] = False
        learners.append(row)
    result["learners"] = learners
    timeline = []
    for raw in result.get("timeline") or []:
        row = dict(raw)
        row.pop("pgy", None)
        row.pop("assessments", None)
        timeline.append(row)
    result["timeline"] = timeline
    return result


def _app(owner):
    return getattr(owner, "app", owner)


def _current_user(owner=None):
    if hasattr(g, "teacher_user"):
        return g.teacher_user
    resolver = getattr(owner, "_current_user", None)
    return resolver() if callable(resolver) else None


def register_training_command_center(owner):
    app = _app(owner)
    if app.extensions.get("teacher_training_command_center_71_registered"):
        return app

    @app.get("/api/training-command-center/profile")
    def training_command_center_profile():
        try:
            return jsonify(audience.current_profile(_current_user(owner)))
        except ApiError as exc:
            return _error(exc)

    @app.get("/api/training-command-center")
    def training_command_center():
        try:
            return jsonify(service.build_summary(_current_user(owner)))
        except ApiError as exc:
            return _error(exc)

    @app.get("/api/training-command-center/pgy-matrix")
    def training_command_center_pgy_matrix():
        try:
            user = _current_user(owner)
            profile = audience.current_profile(user)
            if not profile["pgyLearner"]:
                return jsonify(_online_matrix(profile))
            data = competency.build_competency_matrix(user)
            data["audience"] = "pgy"
            data["pgyLearner"] = True
            return jsonify(data)
        except ApiError as exc:
            return _error(exc)

    @app.get("/api/training-command-center/learning-analytics")
    def training_command_center_learning_analytics():
        try:
            user = _current_user(owner)
            profile = audience.current_profile(user)
            data = analytics.build_learning_analytics(user)
            if not profile["pgyLearner"]:
                data = _suppress_pgy_analytics(data)
            else:
                data["audience"] = "pgy"
                data["pgyLearner"] = True
            return jsonify(data)
        except ApiError as exc:
            return _error(exc)

    app.extensions["teacher_training_command_center_71_registered"] = True
    return app
