"""PGY Blueprint. Not mounted on pgy_app:app in Milestone 2."""

from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from teacher_app.common.errors import ApiError
from teacher_app.pgy import service as pgy_service

bp = Blueprint("pgy", __name__)


def _actor():
    return getattr(g, "pgy_user", None)


def _payload():
    return request.get_json(silent=True) or {}


@bp.errorhandler(ApiError)
def _pgy_api_error(exc: ApiError):
    body = {"ok": False, "error": exc.message, "errorDetail": {"code": exc.code, "message": exc.message}}
    if exc.extra.get("loginRequired"):
        body["loginRequired"] = True
    return jsonify(body), exc.status


@bp.get("/api/pgy/workflow/meta")
def pgy_workflow_meta():
    return jsonify(pgy_service.workflow_meta(_actor()))


@bp.get("/api/pgy/assignment-candidates")
def pgy_assignment_candidates():
    return jsonify(pgy_service.list_assignment_candidates(_actor(), request.args.get("group") or ""))


@bp.get("/api/pgy/assignments")
def pgy_assignments_list():
    return jsonify(
        pgy_service.list_assignments(
            _actor(),
            status=request.args.get("status") or "",
            group=request.args.get("group") or "",
        )
    )


@bp.get("/api/pgy/assignments/<assignment_id>")
def pgy_assignment_get(assignment_id):
    return jsonify(pgy_service.get_assignment(_actor(), assignment_id))


@bp.post("/api/pgy/assignments")
def pgy_assignment_create():
    assignment = pgy_service.create_assignment(_actor(), _payload())
    return jsonify({"ok": True, "assignment": assignment}), 201


@bp.patch("/api/pgy/assignments/<assignment_id>")
def pgy_assignment_update(assignment_id):
    assignment = pgy_service.update_assignment(_actor(), assignment_id, _payload())
    return jsonify({"ok": True, "assignment": assignment})


@bp.post("/api/pgy/assignments/<assignment_id>/submit")
def pgy_assignment_submit(assignment_id):
    assignment = pgy_service.submit_assignment(_actor(), assignment_id, _payload())
    return jsonify({"ok": True, "assignment": assignment})


@bp.post("/api/pgy/assignments/<assignment_id>/teacher-sign")
def pgy_assignment_teacher_sign(assignment_id):
    assignment = pgy_service.teacher_sign_assignment(_actor(), assignment_id, _payload())
    return jsonify({"ok": True, "assignment": assignment})


@bp.post("/api/pgy/assignments/<assignment_id>/countersign")
def pgy_assignment_countersign(assignment_id):
    assignment = pgy_service.group_countersign_assignment(_actor(), assignment_id, _payload())
    return jsonify({"ok": True, "assignment": assignment})


@bp.post("/api/pgy/assignments/<assignment_id>/finalize")
def pgy_assignment_finalize(assignment_id):
    assignment = pgy_service.finalize_assignment(_actor(), assignment_id, _payload())
    return jsonify({"ok": True, "assignment": assignment})


@bp.post("/api/pgy/assignments/<assignment_id>/reopen")
def pgy_assignment_reopen(assignment_id):
    assignment = pgy_service.reopen_assignment(_actor(), assignment_id, _payload())
    return jsonify({"ok": True, "assignment": assignment})


@bp.post("/api/pgy/assignments/<assignment_id>/cancel")
def pgy_assignment_cancel(assignment_id):
    assignment = pgy_service.cancel_assignment(_actor(), assignment_id, _payload())
    return jsonify({"ok": True, "assignment": assignment})


@bp.get("/api/pgy/audit")
def pgy_audit_list():
    return jsonify(pgy_service.list_audit(_actor(), request.args.get("assignmentId") or ""))
