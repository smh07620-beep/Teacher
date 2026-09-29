"""Request-time enforcement for direct material delivery URLs.

Catalog filtering is not a security boundary by itself: a user could otherwise
reuse a remembered /view or /material-preview URL. This guard applies the same
owner-group/audience policy before any provider redirect or file response is
created.
"""
from __future__ import annotations

from flask import abort, g, request

from teacher_app.common import content_audience


def register_content_audience_guard(owner):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_content_audience_guard_registered"):
        return app

    @app.before_request
    def enforce_content_audience_delivery():
        if request.method != "GET":
            return None
        material_id = ""
        if request.endpoint in {"view_material", "material_preview"}:
            material_id = str((request.view_args or {}).get("material_id") or "")
        elif request.endpoint == "uploaded_slide_image":
            material_id = str((request.view_args or {}).get("folder") or "")
        if not material_id:
            return None
        user = getattr(g, "teacher_user", None)
        meta = content_audience._material_meta([material_id]).get(material_id)  # package-internal policy lookup
        if not meta:
            return None
        if not content_audience.visible_to_user(user, meta):
            # Hide existence just like an unavailable material.
            abort(404)
        return None

    app.extensions["teacher_content_audience_guard_registered"] = True
    return app


__all__ = ["register_content_audience_guard"]
