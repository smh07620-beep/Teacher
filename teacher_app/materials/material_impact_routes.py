"""F6 material change impact HTTP surface."""
from __future__ import annotations

from flask import jsonify, request

from teacher_app.common import scope_filter
from teacher_app.materials import material_impact, repository as material_repository


def register_material_impact_routes(app):
    if app.extensions.get("teacher_material_impact_routes_registered"):
        return app

    @app.get("/api/slides/<material_id>/impact")
    def material_change_impact(material_id):
        denied = scope_filter.require_permission(app, "material.manage")
        if denied:
            return denied
        material = material_repository.get_material(material_id)
        if not material:
            return jsonify({"error":"找不到教材"}),404
        _actor, scoped_denied = scope_filter.scoped_groups(
            app,
            "material.manage",
            {str(material.get("group") or "")},
        )
        if scoped_denied:
            return scoped_denied
        raw = str(request.args.get("requiresRetraining") or "").lower()
        requires_retraining = raw in {"1","true","yes","on"}
        try:
            proposed_version = int(request.args.get("proposedVersion") or 0) or None
        except ValueError:
            proposed_version = None
        try:
            return jsonify(
                material_impact.analyze_material_change(
                    _actor,
                    material_id,
                    proposed_version=proposed_version,
                    requires_retraining=requires_retraining,
                )
            )
        except ValueError as exc:
            return jsonify({"error":str(exc)}),400

    app.extensions["teacher_material_impact_routes_registered"]=True
    return app


__all__=["register_material_impact_routes"]
