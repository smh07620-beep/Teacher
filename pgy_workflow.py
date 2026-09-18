"""Thin legacy HTTP adapter for the canonical PGY domain.

The public ``/api/pgy/*`` URLs and legacy JSON error shape remain stable for
cached/older clients and for the 6.6 signing overlay. PGY schema, repository
queries, state transitions, validation and audit writes are canonical in
``teacher_app.pgy``; this module only keeps the compatibility seams still
consumed by ``pgy_signing_66.py``.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from flask import jsonify, request

from teacher_app.common.db import placeholder
from teacher_app.common.errors import ApiError
from teacher_app.pgy import repository as pgy_repo
from teacher_app.pgy import service as pgy_service
from teacher_app.pgy.workflow import (
    ASSIGNMENT_STATUSES,
    WORKFLOW_TRANSITIONS,
    transition_allowed,
    utcnow,
)


# ---------------------------------------------------------------------------
# Compatibility helpers
# ---------------------------------------------------------------------------
# pgy_signing_66 intentionally imports/patches a few of these names. Keep the
# names, but delegate their implementation to the canonical PGY layers.
_json_load = pgy_repo.json_load
_json_dump = pgy_repo.json_dump
_username = pgy_service._username
_text = pgy_service._text
_ph = placeholder


def _role(base, user: Optional[Dict[str, Any]]) -> str:
    return base.normalize_role((user or {}).get("role", "student"))


def _user_group(base, user: Dict[str, Any]) -> str:
    return base.normalize_group(user.get("preferredGroup") or user.get("preferred_group"))


def _auth(base, allowed: Optional[Iterable[str]] = None):
    """Preserve the historical plain-string auth error contract."""
    user = base._current_user()
    if not user:
        return None, (jsonify({"error": "請先登入後再執行此操作。", "loginRequired": True}), 401)
    if allowed is not None:
        normalized = {base.normalize_role(role) for role in allowed}
        if _role(base, user) not in normalized:
            return None, (jsonify({"error": "權限不足。"}), 403)
    return user, None


def init_pgy_workflow_db(base) -> None:
    """Keep the legacy startup hook while making schema ownership canonical."""
    conn, kind = base._db_conn()
    try:
        pgy_repo.init_schema(conn, kind)
    finally:
        conn.close()


def _lookup_account(conn, kind: str, username: str):
    return pgy_repo.find_user(conn, kind, username)


def _course_row(conn, kind: str, course_id: str):
    return pgy_repo.find_course(conn, kind, course_id)


def _assignment_query() -> str:
    return pgy_repo.ASSIGNMENT_COLUMNS


# Deliberately assign, rather than wrap: pgy_signing_66 decorates this symbol
# to extend the legacy assignment JSON contract with signing metadata.
_assignment_dict = pgy_repo.assignment_dict


def _get_assignment(conn, kind: str, assignment_id: str):
    return pgy_repo.get_assignment(conn, kind, assignment_id)


def _can_view(base, user: Dict[str, Any], row) -> bool:
    return pgy_service._can_view(user, dict(row))


def _audit(
    conn,
    kind: str,
    base,
    assignment_id: str,
    user: Dict[str, Any],
    action: str,
    from_status: str = "",
    to_status: str = "",
    detail: Optional[Dict[str, Any]] = None,
) -> None:
    pgy_repo.write_audit(
        conn,
        kind,
        assignment_id=assignment_id,
        action=action,
        from_status=from_status,
        to_status=to_status,
        actor_username=_username(user.get("username")),
        actor_role=_role(base, user),
        detail=detail or {},
    )


def _legacy_error_body(exc: ApiError) -> dict:
    """Stable legacy PGY error projection used by compatibility adapters."""
    body = {"error": exc.message}
    if exc.extra.get("loginRequired"):
        body["loginRequired"] = True
    return body


def _legacy_error(exc: ApiError):
    return jsonify(_legacy_error_body(exc)), exc.status


def _assignment_response(handler, user, assignment_id: str, data: Dict[str, Any]):
    try:
        assignment = handler(user, assignment_id, data)
        return jsonify({"ok": True, "assignment": assignment})
    except ApiError as exc:
        return _legacy_error(exc)


# ---------------------------------------------------------------------------
# Legacy route surface -> canonical PGY service
# ---------------------------------------------------------------------------
def register_pgy_workflow(base):
    """Register unchanged legacy URLs as thin canonical-service delegates."""
    app = base.app
    if app.extensions.get("pgy_workflow_registered"):
        return app
    init_pgy_workflow_db(base)
    app.extensions["pgy_workflow_registered"] = True

    @app.get("/api/pgy/workflow/meta")
    def pgy_workflow_meta():
        user, denied = _auth(base)
        if denied:
            return denied
        try:
            return jsonify(pgy_service.workflow_meta(user))
        except ApiError as exc:
            return _legacy_error(exc)

    @app.get("/api/pgy/assignment-candidates")
    def pgy_assignment_candidates():
        user, denied = _auth(base, {"education_admin", "group_leader"})
        if denied:
            return denied
        try:
            return jsonify(pgy_service.list_assignment_candidates(user, request.args.get("group", "")))
        except ApiError as exc:
            return _legacy_error(exc)

    @app.get("/api/pgy/assignments")
    def pgy_assignments_list():
        user, denied = _auth(base, {"student", "clinical_teacher", "group_leader", "education_admin"})
        if denied:
            return denied
        try:
            return jsonify(
                pgy_service.list_assignments(
                    user,
                    status=request.args.get("status", ""),
                    group=request.args.get("group", ""),
                )
            )
        except ApiError as exc:
            return _legacy_error(exc)

    @app.get("/api/pgy/assignments/<assignment_id>")
    def pgy_assignment_get(assignment_id):
        user, denied = _auth(base, {"student", "clinical_teacher", "group_leader", "education_admin"})
        if denied:
            return denied
        try:
            return jsonify(pgy_service.get_assignment(user, assignment_id))
        except ApiError as exc:
            return _legacy_error(exc)

    @app.post("/api/pgy/assignments")
    def pgy_assignment_create():
        user, denied = _auth(base, {"education_admin"})
        if denied:
            return denied
        try:
            assignment = pgy_service.create_assignment(user, request.get_json(silent=True) or {})
            return jsonify({"ok": True, "assignment": assignment}), 201
        except ApiError as exc:
            return _legacy_error(exc)

    @app.patch("/api/pgy/assignments/<assignment_id>")
    def pgy_assignment_update(assignment_id):
        user, denied = _auth(base, {"student", "education_admin"})
        if denied:
            return denied
        return _assignment_response(
            pgy_service.update_assignment,
            user,
            assignment_id,
            request.get_json(silent=True) or {},
        )

    @app.post("/api/pgy/assignments/<assignment_id>/submit")
    def pgy_assignment_submit(assignment_id):
        user, denied = _auth(base, {"student"})
        if denied:
            return denied
        return _assignment_response(
            pgy_service.submit_assignment,
            user,
            assignment_id,
            request.get_json(silent=True) or {},
        )

    @app.post("/api/pgy/assignments/<assignment_id>/teacher-sign")
    def pgy_assignment_teacher_sign(assignment_id):
        user, denied = _auth(base, {"clinical_teacher"})
        if denied:
            return denied
        return _assignment_response(
            pgy_service.teacher_sign_assignment,
            user,
            assignment_id,
            request.get_json(silent=True) or {},
        )

    @app.post("/api/pgy/assignments/<assignment_id>/countersign")
    def pgy_assignment_countersign(assignment_id):
        user, denied = _auth(base, {"group_leader"})
        if denied:
            return denied
        return _assignment_response(
            pgy_service.group_countersign_assignment,
            user,
            assignment_id,
            request.get_json(silent=True) or {},
        )

    @app.post("/api/pgy/assignments/<assignment_id>/finalize")
    def pgy_assignment_finalize(assignment_id):
        user, denied = _auth(base, {"education_admin"})
        if denied:
            return denied
        return _assignment_response(
            pgy_service.finalize_assignment,
            user,
            assignment_id,
            request.get_json(silent=True) or {},
        )

    @app.post("/api/pgy/assignments/<assignment_id>/reopen")
    def pgy_assignment_reopen(assignment_id):
        user, denied = _auth(base, {"education_admin"})
        if denied:
            return denied
        return _assignment_response(
            pgy_service.reopen_assignment,
            user,
            assignment_id,
            request.get_json(silent=True) or {},
        )

    @app.post("/api/pgy/assignments/<assignment_id>/cancel")
    def pgy_assignment_cancel(assignment_id):
        user, denied = _auth(base, {"education_admin"})
        if denied:
            return denied
        return _assignment_response(
            pgy_service.cancel_assignment,
            user,
            assignment_id,
            request.get_json(silent=True) or {},
        )

    @app.get("/api/pgy/audit")
    def pgy_audit_list():
        user, denied = _auth(base, {"auditor", "system_admin", "education_admin", "group_leader"})
        if denied:
            return denied
        try:
            return jsonify(pgy_service.list_audit(user, request.args.get("assignmentId", "")))
        except ApiError as exc:
            return _legacy_error(exc)

    return app
