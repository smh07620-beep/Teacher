"""F6 read-only production acceptance API for system administrators."""
from __future__ import annotations

from flask import jsonify

from teacher_app.common import scope_filter
from teacher_app.maintenance import production_readiness as production_readiness_service


def register_production_readiness_routes(app, *, material_runtime, connection_factory=None):
    if app.extensions.get("teacher_production_readiness_registered"):
        return app

    @app.get("/api/production-readiness")
    def production_readiness():
        denied = scope_filter.require_permission(app, "system.manage")
        if denied:
            return denied
        return jsonify(
            production_readiness_service.build_acceptance(
                material_runtime=material_runtime,
                connection_factory=connection_factory,
            )
        )

    app.extensions["teacher_production_readiness_registered"] = True
    return app


__all__ = ["register_production_readiness_routes"]
