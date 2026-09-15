"""Legacy PGY route adapter for Teacher 6.5 Milestone 2B.

The public Flask endpoints and legacy response contract stay owned by
``pgy_app:app``.  Business rules, conditional status updates, transactions and
audit writes now live in ``teacher_app.pgy.service`` / ``repository`` so there
is only one implementation of the six atomic PGY transitions.
"""
from __future__ import annotations

from flask import jsonify, request

import pgy_workflow as wf
from teacher_app.common.errors import ApiError
from teacher_app.pgy import service as pgy_service


_ACTIONS = {
    "submit": ("student", pgy_service.submit_assignment),
    "teacher_sign": ("clinical_teacher", pgy_service.teacher_sign_assignment),
    "group_countersign": ("group_leader", pgy_service.group_countersign_assignment),
    "finalize": ("education_admin", pgy_service.finalize_assignment),
}


def _legacy_error_body(exc: ApiError) -> dict:
    """Keep the 6.4/legacy JSON contract: ``error`` remains a plain string."""
    body = {"error": exc.message}
    if exc.extra.get("loginRequired"):
        body["loginRequired"] = True
    return body


def _legacy_service_response(callable_, user, assignment_id: str, data: dict):
    try:
        assignment = callable_(user, assignment_id, data)
        return jsonify({"ok": True, "assignment": assignment})
    except ApiError as exc:
        return jsonify(_legacy_error_body(exc)), exc.status


def register_pgy_atomic_workflow(base):
    app = base.app
    if app.extensions.get("pgy_atomic_registered"):
        return app
    app.extensions["pgy_atomic_registered"] = True

    def workflow_action(assignment_id: str, action: str):
        required_role, handler = _ACTIONS[action]
        # Preserve the old authentication/authorization response exactly.
        user, denied = wf._auth(base, {required_role})
        if denied:
            return denied
        data = request.get_json(silent=True) or {}
        return _legacy_service_response(handler, user, assignment_id, data)

    def submit(assignment_id):
        return workflow_action(assignment_id, "submit")

    def teacher_sign(assignment_id):
        return workflow_action(assignment_id, "teacher_sign")

    def countersign(assignment_id):
        return workflow_action(assignment_id, "group_countersign")

    def finalize(assignment_id):
        return workflow_action(assignment_id, "finalize")

    def reopen(assignment_id):
        user, denied = wf._auth(base, {"education_admin"})
        if denied:
            return denied
        data = request.get_json(silent=True) or {}
        return _legacy_service_response(pgy_service.reopen_assignment, user, assignment_id, data)

    def cancel(assignment_id):
        user, denied = wf._auth(base, {"education_admin"})
        if denied:
            return denied
        data = request.get_json(silent=True) or {}
        return _legacy_service_response(pgy_service.cancel_assignment, user, assignment_id, data)

    # Replace only the six legacy mutation view functions. URL rules, endpoint
    # names and all read/create/update APIs remain unchanged.
    app.view_functions["pgy_assignment_submit"] = submit
    app.view_functions["pgy_assignment_teacher_sign"] = teacher_sign
    app.view_functions["pgy_assignment_countersign"] = countersign
    app.view_functions["pgy_assignment_finalize"] = finalize
    app.view_functions["pgy_assignment_reopen"] = reopen
    app.view_functions["pgy_assignment_cancel"] = cancel
    return app
