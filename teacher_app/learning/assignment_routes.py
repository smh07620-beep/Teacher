"""HTTP management surface for general learning assignments."""
from __future__ import annotations

from flask import g, jsonify, request

from teacher_app.auth import repository as auth_repository
from teacher_app.common import audit, scope_filter
from teacher_app.common.auth import has_role
from teacher_app.common.errors import ApiError
from teacher_app.courses import repository as course_repository
from teacher_app.learning import assignment_repository, assignment_service


def _actor(owner=None):
    user = getattr(g, "teacher_user", None)
    if user is not None:
        return user
    resolver = getattr(owner, "_current_user", None)
    return resolver() if callable(resolver) else None


def _course(course_id: str) -> dict:
    course = course_repository.get_course(str(course_id or "").strip())
    if not course:
        raise ApiError("COURSE_NOT_FOUND", "找不到課程。", status=404)
    return course


def _guard_course(owner, course: dict):
    group = str(course.get("group") or "").strip()
    _user, denied = scope_filter.scoped_groups(owner, "course.manage", {group})
    return denied


def _error(exc: ApiError):
    payload = {"error": exc.message, "code": exc.code}
    payload.update(exc.extra)
    return jsonify(payload), exc.status


def _can_cross_group(user) -> bool:
    return bool(user) and (
        has_role(user, "education_admin") or has_role(user, "system_admin")
    )


def _user_public(row) -> dict:
    row = dict(row or {})
    return {
        "username": str(row.get("username") or ""),
        "name": str(row.get("display_name") or ""),
        "empId": str(row.get("emp_id") or ""),
        "area": str(row.get("preferred_area") or "internal"),
        "group": str(row.get("preferred_group") or "grpBio"),
        "active": bool(row.get("active", True)),
    }


def _assignment_snapshot(item: dict) -> dict:
    return {
        key: item.get(key)
        for key in (
            "id", "courseId", "area", "group", "assigneeType", "assigneeKey",
            "required", "dueAt", "assignedAt", "assignedBy", "active",
        )
    }


def register_learning_assignment_routes(owner):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_learning_assignment_routes_registered"):
        return app

    @app.get("/api/learning-assignments")
    def learning_assignments_list():
        try:
            course = _course(request.args.get("courseId", ""))
        except ApiError as exc:
            return _error(exc)
        denied = _guard_course(owner, course)
        if denied:
            return denied
        rows = assignment_repository.list_for_course(course["id"])
        users = {str(row.get("username") or "").lower(): _user_public(row) for row in auth_repository.list_users()}
        for row in rows:
            if row.get("assigneeType") == "user":
                row["assignee"] = users.get(str(row.get("assigneeKey") or "").lower())
        return jsonify({"course": course, "assignments": rows})

    @app.get("/api/learning-assignments/candidates")
    def learning_assignment_candidates():
        try:
            course = _course(request.args.get("courseId", ""))
        except ApiError as exc:
            return _error(exc)
        denied = _guard_course(owner, course)
        if denied:
            return denied
        actor = _actor(owner)
        global_manager = _can_cross_group(actor)
        candidates = []
        for raw in auth_repository.list_users():
            item = _user_public(raw)
            if not item["active"]:
                continue
            if not global_manager and (
                item["area"] != course.get("area") or item["group"] != course.get("group")
            ):
                continue
            candidates.append(item)
        return jsonify({
            "course": {"id": course["id"], "title": course.get("title", ""), "area": course.get("area", ""), "group": course.get("group", "")},
            "canAssignAll": global_manager,
            "canAssignCrossGroupUser": global_manager,
            "users": candidates,
        })

    @app.post("/api/learning-assignments")
    def learning_assignment_create():
        actor = _actor(owner)
        data = request.get_json(silent=True) or {}
        try:
            course = _course(data.get("courseId", ""))
        except ApiError as exc:
            return _error(exc)
        denied = _guard_course(owner, course)
        if denied:
            return denied
        assignee_type = str(data.get("assigneeType") or "").strip().lower()
        if assignee_type == "all" and not _can_cross_group(actor):
            return jsonify({"error": "只有教學管理者或系統管理者可建立全體指派。"}), 403
        if assignee_type == "user":
            target = auth_repository.find_user(str(data.get("assigneeKey") or "").strip().lower())
            if not target or not bool(target.get("active", True)):
                return jsonify({"error": "找不到可指派的使用者。"}), 404
            if not _can_cross_group(actor) and (
                str(target.get("preferred_area") or "internal") != str(course.get("area") or "")
                or str(target.get("preferred_group") or "grpBio") != str(course.get("group") or "")
            ):
                return jsonify({"error": "此學員不在你的課程管理範圍。"}), 403
        try:
            assignment = assignment_service.create_assignment(actor or {}, data)
        except ApiError as exc:
            return _error(exc)
        audit.record_event(
            actor=actor,
            action="learning_assignment.create",
            target_type="learning_assignment",
            target_id=str(assignment.get("id") or ""),
            group=str(course.get("group") or ""),
            scope={"area": course.get("area"), "courseId": course.get("id")},
            after=_assignment_snapshot(assignment),
        )
        return jsonify({"ok": True, "assignment": assignment}), 201

    @app.delete("/api/learning-assignments/<assignment_id>")
    def learning_assignment_deactivate(assignment_id):
        actor = _actor(owner)
        before = assignment_repository.get_assignment(assignment_id)
        if not before:
            return jsonify({"error": "找不到學習指派。"}), 404
        try:
            course = _course(before.get("courseId", ""))
        except ApiError as exc:
            return _error(exc)
        denied = _guard_course(owner, course)
        if denied:
            return denied
        after = assignment_service.deactivate_assignment(assignment_id)
        audit.record_event(
            actor=actor,
            action="learning_assignment.deactivate",
            target_type="learning_assignment",
            target_id=assignment_id,
            group=str(course.get("group") or ""),
            scope={"area": course.get("area"), "courseId": course.get("id")},
            before=_assignment_snapshot(before),
            after=_assignment_snapshot(after),
        )
        return jsonify({"ok": True, "assignment": after})

    app.extensions["teacher_learning_assignment_routes_registered"] = True
    return app


__all__ = ["register_learning_assignment_routes"]
