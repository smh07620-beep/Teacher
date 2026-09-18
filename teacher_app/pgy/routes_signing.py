"""Canonical HTTP overlay for PGY 6.6 signing behavior."""
from __future__ import annotations

from flask import jsonify, request

from teacher_app.common import db as common_db
from teacher_app.common.errors import ApiError
from teacher_app.pgy import signing, signing_facade


def _error(exc: ApiError):
    body = {"error": exc.message}
    if exc.extra.get("loginRequired"):
        body["loginRequired"] = True
    return jsonify(body), exc.status


def _current_user(base):
    user = base._current_user()
    if not user:
        raise ApiError(
            "LOGIN_REQUIRED",
            "請先登入後再執行此操作。",
            status=401,
            extra={"loginRequired": True},
        )
    return user


def register_pgy_signing_66(base):
    app = base.app
    if app.extensions.get("teacher_pgy_signing_66_registered"):
        return app

    with common_db.transaction() as (conn, kind):
        signing.ensure_schema_connection(conn, kind)

    def workflow_meta():
        try:
            return jsonify(signing_facade.workflow_meta(_current_user(base)))
        except ApiError as exc:
            return _error(exc)

    app.view_functions["pgy_workflow_meta"] = workflow_meta

    def candidates():
        try:
            return jsonify(signing_facade.list_candidates(
                _current_user(base),
                request.args.get("group", ""),
            ))
        except ApiError as exc:
            return _error(exc)

    app.view_functions["pgy_assignment_candidates"] = candidates

    def list_assignments():
        try:
            return jsonify(signing_facade.list_assignments(
                _current_user(base),
                status=request.args.get("status", ""),
                group=request.args.get("group", ""),
            ))
        except ApiError as exc:
            return _error(exc)

    app.view_functions["pgy_assignments_list"] = list_assignments

    def assignment_get(assignment_id):
        try:
            return jsonify(signing_facade.get_assignment(_current_user(base), assignment_id))
        except ApiError as exc:
            return _error(exc)

    app.view_functions["pgy_assignment_get"] = assignment_get

    def create_assignment():
        try:
            assignment = signing_facade.create_assignment(
                _current_user(base),
                request.get_json(silent=True) or {},
            )
            return jsonify({"ok": True, "assignment": assignment}), 201
        except ApiError as exc:
            return _error(exc)

    app.view_functions["pgy_assignment_create"] = create_assignment

    def update_assignment(assignment_id):
        try:
            assignment = signing_facade.update_assignment(
                _current_user(base),
                assignment_id,
                request.get_json(silent=True) or {},
            )
            return jsonify({"ok": True, "assignment": assignment})
        except ApiError as exc:
            return _error(exc)

    app.view_functions["pgy_assignment_update"] = update_assignment

    def teacher_sign(assignment_id):
        try:
            assignment = signing_facade.teacher_sign_assignment(
                _current_user(base),
                assignment_id,
                request.get_json(silent=True) or {},
            )
            return jsonify({"ok": True, "assignment": assignment})
        except ApiError as exc:
            return _error(exc)

    app.view_functions["pgy_assignment_teacher_sign"] = teacher_sign

    def countersign(assignment_id):
        try:
            assignment = signing_facade.countersign_assignment(
                _current_user(base),
                assignment_id,
                request.get_json(silent=True) or {},
            )
            return jsonify({"ok": True, "assignment": assignment})
        except ApiError as exc:
            return _error(exc)

    app.view_functions["pgy_assignment_countersign"] = countersign

    def reopen(assignment_id):
        try:
            assignment = signing_facade.reopen_assignment(
                _current_user(base),
                assignment_id,
                request.get_json(silent=True) or {},
            )
            return jsonify({"ok": True, "assignment": assignment})
        except ApiError as exc:
            return _error(exc)

    app.view_functions["pgy_assignment_reopen"] = reopen
    app.extensions["teacher_pgy_signing_66_registered"] = True
    return app


__all__ = ["register_pgy_signing_66"]
