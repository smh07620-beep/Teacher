"""HTTP adapter for Teacher 7.1 Training Command Center."""

from __future__ import annotations

from flask import jsonify

from teacher_app.command_center import service
from teacher_app.common.errors import ApiError


def _error(exc: ApiError):
    body = {"error": exc.message}
    body.update(exc.extra)
    return jsonify(body), exc.status


def register_training_command_center(base):
    app = base.app
    if app.extensions.get("teacher_training_command_center_71_registered"):
        return app

    @app.get("/api/training-command-center")
    def training_command_center():
        try:
            return jsonify(service.build_summary(base._current_user()))
        except ApiError as exc:
            return _error(exc)

    app.extensions["teacher_training_command_center_71_registered"] = True
    return app
