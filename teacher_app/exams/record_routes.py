"""Canonical legacy-compatible exam-record HTTP routes."""
from __future__ import annotations

import hmac
import os

from flask import g, jsonify, request

from teacher_app.common.auth import has_permission
from teacher_app.exams import records


def _app(owner):
    return getattr(owner, "app", owner)


def _current_user(owner=None):
    if hasattr(g, "teacher_user"):
        return g.teacher_user
    resolver = getattr(owner, "_current_user", None)
    return resolver() if callable(resolver) else None


def _require_admin(owner=None):
    supplied = str(request.headers.get("X-Admin-Key", "") or "")
    admin_key = os.environ.get("ADMIN_KEY", "").strip()
    if admin_key and supplied and hmac.compare_digest(supplied, admin_key):
        return None
    user = _current_user(owner)
    if not user:
        return jsonify({
            "error": "請先以管理者帳號登入，或提供正確的 ADMIN_KEY。",
            "loginRequired": True,
        }), 401
    if not (
        has_permission(user, "user.manage")
        or has_permission(user, "system.manage")
    ):
        return jsonify({"error": "權限不足：此功能限教學管理者使用。"}), 403
    return None


def register_record_routes(owner):
    app = _app(owner)
    if app.extensions.get("teacher_record_routes_registered"):
        return app

    def api_review_record(record_id):
        denied = _require_admin(owner)
        if denied:
            return denied
        try:
            return jsonify(records.review_record(record_id, request.get_json(silent=True) or {}))
        except records.RecordError as exc:
            return jsonify({"error": str(exc)}), exc.status

    def api_create_record():
        user = _current_user(owner)
        if not user:
            return jsonify({"error": "請先登入後再使用教材。", "loginRequired": True}), 401
        try:
            record_id = records.create_record(user, request.get_json(silent=True) or {})
        except records.RecordError as exc:
            return jsonify({"error": str(exc)}), exc.status
        return jsonify({"ok": True, "id": record_id})

    def api_list_records():
        denied = _require_admin(owner)
        if denied:
            return denied
        return jsonify(records.list_records())

    def api_clear_records():
        denied = _require_admin(owner)
        if denied:
            return denied
        records.clear_records()
        return jsonify({"ok": True})

    app.add_url_rule("/api/records/<record_id>/review", endpoint="api_review_record", view_func=api_review_record, methods=["PATCH"])
    app.add_url_rule("/api/records", endpoint="api_create_record", view_func=api_create_record, methods=["POST"])
    app.add_url_rule("/api/records", endpoint="api_list_records", view_func=api_list_records, methods=["GET"])
    app.add_url_rule("/api/records", endpoint="api_clear_records", view_func=api_clear_records, methods=["DELETE"])
    app.extensions["teacher_record_routes_registered"] = True
    return app


__all__ = ["register_record_routes"]
