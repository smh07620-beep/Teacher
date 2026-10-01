"""Canonical legacy-compatible exam-record HTTP routes."""
from __future__ import annotations

from flask import g, jsonify, request

from teacher_app.common import audit, scope
from teacher_app.common.auth import ROLE_LABELS, has_permission, has_role, normalize_role
from teacher_app.exams import records


def _app(owner):
    return getattr(owner, "app", owner)


def _current_user(owner=None):
    if hasattr(g, "teacher_user"):
        return g.teacher_user
    resolver = getattr(owner, "_current_user", None)
    return resolver() if callable(resolver) else None


def _require_admin(owner=None):
    user = _current_user(owner)
    if not user:
        return jsonify({
            "error": "請先以管理者帳號登入。",
            "loginRequired": True,
        }), 401
    if not has_permission(user, "system.manage"):
        return jsonify({"error": "權限不足：此功能限系統管理者使用。"}), 403
    return None


def _review_identity(user):
    user = user or {}
    name = str(user.get("name") or user.get("username") or "").strip()[:100]
    title = str(user.get("professionalTitle") or "").strip()[:100]
    if not title:
        title = ROLE_LABELS.get(normalize_role(user.get("role")), "")[:100]
    return name, title


def _review_denied(owner, record):
    """Authorize exam grading without widening a teacher's resource scope."""
    user = _current_user(owner)
    if not user:
        return jsonify({"error": "請先登入後再進行批改。", "loginRequired": True}), 401
    if not has_permission(user, "exam.manage"):
        return jsonify({"error": "權限不足：此功能限具考核管理權限的教師使用。"}), 403
    if has_role(user, "system_admin") or has_role(user, "education_admin"):
        return None

    actor_area = scope.normalize_area(user.get("preferredArea"))
    actor_group = scope.normalize_group(user.get("preferredGroup"))
    record_area = scope.normalize_area((record or {}).get("trainingArea"))
    record_group = scope.normalize_group((record or {}).get("groupKey"))
    if actor_area != record_area or actor_group != record_group:
        return jsonify({"error": "此考核紀錄不在你的教學組別範圍。"}), 403
    return None


def _review_audit_snapshot(record):
    record = record or {}
    return {
        "score": record.get("score"),
        "status": str(record.get("status") or ""),
        "reviewStatus": str(record.get("reviewStatus") or ""),
        "reviewedAt": str(record.get("reviewedAt") or ""),
        "reviewerName": str(record.get("reviewerName") or ""),
        "evaluatorName": str(record.get("evaluatorName") or ""),
        "evaluatorTitle": str(record.get("evaluatorTitle") or ""),
    }


def register_record_routes(owner):
    app = _app(owner)
    if app.extensions.get("teacher_record_routes_registered"):
        return app

    def api_review_record(record_id):
        before = records.get_record(record_id)
        if not before:
            return jsonify({"error": "找不到考試紀錄"}), 404
        denied = _review_denied(owner, before)
        if denied:
            return denied

        actor = _current_user(owner) or {}
        reviewer_name, reviewer_title = _review_identity(actor)
        data = dict(request.get_json(silent=True) or {})
        # Never trust browser-provided reviewer identity.  The authenticated
        # account is the only authority for final reviewer/evaluator fields.
        data.pop("reviewerName", None)
        data.pop("reviewerTitle", None)
        try:
            result = records.review_record(
                record_id,
                data,
                reviewer_name=reviewer_name,
                reviewer_title=reviewer_title,
            )
        except records.RecordError as exc:
            return jsonify({"error": str(exc)}), exc.status

        after = records.get_record(record_id) or {}
        audit.record_event(
            actor=actor,
            action="exam.record.review",
            target_type="exam_record",
            target_id=record_id,
            group=str(after.get("groupKey") or before.get("groupKey") or ""),
            before=_review_audit_snapshot(before),
            after=_review_audit_snapshot(after),
            detail={
                "reviewerDerivedFromSession": True,
                "trainingArea": str(after.get("trainingArea") or before.get("trainingArea") or ""),
            },
        )
        return jsonify(result)

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