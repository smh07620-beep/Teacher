"""Manager-facing training compliance matrix API."""
from __future__ import annotations

from flask import g, jsonify, request

from teacher_app.learning import compliance_service


def register_training_compliance_routes(app):
    if app.extensions.get("teacher_training_compliance_91_registered"):
        return app

    @app.get("/api/training-compliance")
    def training_compliance_matrix():
        return jsonify(
            compliance_service.build_matrix(
                getattr(g, "teacher_user", None),
                area=request.args.get("area", ""),
                group=request.args.get("group", ""),
                course_id=request.args.get("courseId", ""),
                status=request.args.get("status", ""),
                include_inactive_users=request.args.get(
                    "includeInactiveUsers", ""
                ).lower()
                in {"1", "true", "yes"},
            )
        )

    app.extensions["teacher_training_compliance_91_registered"] = True
    return app


__all__ = ["register_training_compliance_routes"]
