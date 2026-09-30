"""HTTP adapters for general course assignments."""
from __future__ import annotations

from flask import g, jsonify, request

from teacher_app.common import audit
from teacher_app.common.auth import has_role
from teacher_app.common.errors import ApiError
from teacher_app.learning import assignment_service


def _app(owner):
    return getattr(owner, "app", owner)


def _user(owner=None):
    user = getattr(g, "teacher_user", None)
    if user is not None:
        return user
    resolver = getattr(owner, "_current_user", None)
    return resolver() if callable(resolver) else None


def _error(exc: ApiError):
    body = {"error": exc.message, "code": exc.code}
    body.update(exc.extra)
    return jsonify(body), exc.status


def _group_leader_scoped(actor) -> bool:
    """True for a group leader without organization/system-wide assignment scope."""
    return bool(
        actor
        and has_role(actor, "group_leader")
        and not has_role(actor, "education_admin")
        and not has_role(actor, "system_admin")
    )


def _normalize_create_payload(actor, payload):
    """Map leader-facing 'all' to the course's existing group scope.

    ``assignment_service`` remains authoritative for course lookup and scope
    validation. A leader's 'all personnel' therefore means everyone eligible
    inside that course/group scope; it never creates an organization-wide row.
    """
    data = dict(payload or {})
    if _group_leader_scoped(actor) and str(data.get("assigneeType") or "").strip().lower() == "all":
        data["assigneeType"] = "group"
        data["assigneeKey"] = ""
    return data


def _audience_options_for_actor(actor, options):
    body = dict(options or {})
    if _group_leader_scoped(actor):
        allowed = [str(value) for value in (body.get("allowedAssigneeTypes") or [])]
        if "all" not in allowed:
            allowed.append("all")
        body["allowedAssigneeTypes"] = allowed
        body["allScope"] = "course_group"
    return body


def register_learning_assignment_routes(owner):
    app = _app(owner)
    if app.extensions.get("teacher_learning_assignment_routes_registered"):
        return app

    @app.get("/api/learning-assignments/mine")
    def learning_assignments_mine():
        try:
            return jsonify(assignment_service.mine(_user(owner)))
        except ApiError as exc:
            return _error(exc)

    @app.get("/api/learning-assignments/audience-options")
    def learning_assignments_audience_options():
        actor = _user(owner)
        try:
            options = assignment_service.audience_options(
                actor,
                area=request.args.get("area", ""),
                group=request.args.get("group", ""),
            )
            return jsonify(_audience_options_for_actor(actor, options))
        except ApiError as exc:
            return _error(exc)

    @app.get("/api/learning-assignments")
    def learning_assignments_admin_list():
        try:
            include_raw = request.args.get(
                "includeInactive",
                request.args.get("includeCancelled", ""),
            )
            rows = assignment_service.admin_list(
                _user(owner),
                area=request.args.get("area", ""),
                group=request.args.get("group", ""),
                include_inactive=str(include_raw).lower() in {"1", "true", "yes", "on"},
            )
            return jsonify(rows)
        except ApiError as exc:
            return _error(exc)

    @app.post("/api/learning-assignments")
    def learning_assignments_create():
        actor = _user(owner)
        try:
            assignment = assignment_service.create_assignment(
                actor,
                _normalize_create_payload(actor, request.get_json(silent=True) or {}),
            )
        except ApiError as exc:
            return _error(exc)
        audit.record_event(
            actor=actor,
            action="learning.assignment.create",
            target_type="learning_assignment",
            target_id=assignment.get("id", ""),
            group=assignment.get("group", ""),
            after=assignment,
        )
        return jsonify({"ok": True, "assignment": assignment}), 201

    @app.patch("/api/learning-assignments/<assignment_id>")
    def learning_assignments_update(assignment_id):
        actor = _user(owner)
        from teacher_app.learning import assignment_repository

        before = assignment_repository.get_assignment(assignment_id)
        try:
            assignment = assignment_service.update_assignment(
                actor,
                assignment_id,
                request.get_json(silent=True) or {},
            )
        except ApiError as exc:
            return _error(exc)
        audit.record_event(
            actor=actor,
            action="learning.assignment.update",
            target_type="learning_assignment",
            target_id=assignment.get("id", assignment_id),
            group=assignment.get("group", ""),
            before=before,
            after=assignment,
        )
        return jsonify({"ok": True, "assignment": assignment})

    app.extensions["teacher_learning_assignment_routes_registered"] = True
    return app


__all__ = ["register_learning_assignment_routes"]
