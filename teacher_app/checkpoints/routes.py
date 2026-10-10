"""HTTP routes for optional in-slide checkpoint questions."""
from __future__ import annotations

from typing import Callable

from flask import g, jsonify, request

from teacher_app.checkpoints import service
from teacher_app.common.errors import ApiError


def _error(exc: ApiError):
    body = {"error": exc.message}
    body.update(exc.extra or {})
    return jsonify(body), exc.status


def register_slide_checkpoints(app, *, material_getter: Callable):
    def user_or_denied():
        user = getattr(g, "teacher_user", None)
        if not user:
            return None, (jsonify({"error": "請先登入。", "loginRequired": True}), 401)
        return user, None

    def guarded(fn):
        user, denied = user_or_denied()
        if denied:
            return denied
        try:
            return fn(user)
        except ApiError as exc:
            return _error(exc)

    @app.get("/api/materials/<material_id>/checkpoints", endpoint="slide_checkpoints_learner")
    def learner_list(material_id):
        return guarded(lambda user: jsonify(service.list_for_learner(user, material_getter, material_id)))

    @app.get("/api/materials/<material_id>/checkpoints/manage", endpoint="slide_checkpoints_manage")
    def manager_list(material_id):
        return guarded(lambda user: jsonify(service.list_for_manager(user, material_getter, material_id)))

    @app.post("/api/materials/<material_id>/checkpoints", endpoint="slide_checkpoints_create")
    def create(material_id):
        body = request.get_json(silent=True) or {}
        return guarded(lambda user: (jsonify({"ok": True, "item": service.create(user, material_getter, material_id, body)}), 201))

    @app.patch("/api/slide-checkpoints/<checkpoint_id>", endpoint="slide_checkpoints_update")
    def update(checkpoint_id):
        body = request.get_json(silent=True) or {}
        return guarded(lambda user: jsonify({"ok": True, "item": service.update(user, material_getter, checkpoint_id, body)}))

    @app.delete("/api/slide-checkpoints/<checkpoint_id>", endpoint="slide_checkpoints_delete")
    def delete(checkpoint_id):
        def run(user):
            service.delete(user, material_getter, checkpoint_id)
            return jsonify({"ok": True})
        return guarded(run)

    @app.post("/api/slide-checkpoints/<checkpoint_id>/answer", endpoint="slide_checkpoints_answer")
    def answer(checkpoint_id):
        body = request.get_json(silent=True) or {}
        return guarded(lambda user: jsonify(service.answer(user, material_getter, checkpoint_id, body)))

    return app
