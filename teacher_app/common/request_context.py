"""Canonical request-scoped bindings shared by modular HTTP routes."""
from __future__ import annotations

from flask import g, session

from teacher_app.auth import service as auth_service


def register_request_context(app, *, current_user=None):
    """Bind the authenticated actor once per request from the canonical session.

    Session resolution is package-owned and no domain ``base`` object is stored
    in ``g``.
    """
    if app.extensions.get("teacher_request_context_registered"):
        return app

    resolve_user = current_user or (
        lambda: auth_service.current_user(session, include_roles=True)
    )

    @app.before_request
    def bind_teacher_request_context():
        user = resolve_user()
        g.teacher_user = user
        g.pgy_user = user
        g.exam_user = user

    app.extensions["teacher_request_context_registered"] = True
    return app


__all__ = ["register_request_context"]
