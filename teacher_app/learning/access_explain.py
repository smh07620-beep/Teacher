"""Explain, step by step, why a person can or cannot see a course, material or exam.

Read-only diagnosis for administrators.  Every step calls the same functions the
learner screens use (``learning.access``), so the explanation cannot drift from
the real rule; the final verdict is the real rule's own answer.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Mapping

from teacher_app.common import scope
from teacher_app.common.auth import user_roles
from teacher_app.learning import access


def _step(name: str, passed: bool, reason: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "reason": reason}


def _course_for(kind: str, item: Mapping[str, Any]) -> str:
    return str(item.get("id") or "") if kind == "course" else str(item.get("courseId") or item.get("course_id") or "")


def _window_step(category_id: str) -> dict[str, Any] | None:
    try:
        from teacher_app.exams import windows

        window = windows.get_window(category_id)
    except Exception:
        return None
    if not window:
        return _step("考試時間", True, "沒有設定開放期間。")
    now = dt.datetime.now(dt.timezone.utc)
    for field, label, before in (("opens_at", "尚未開放", True), ("closes_at", "已截止", False)):
        try:
            value = windows._window_time(window.get(field))
        except Exception:
            value = None
        if value and ((before and now < value) or (not before and now > value)):
            return _step("考試時間", False, f"此考卷{label}。")
    return _step("考試時間", True, "目前在開放期間內。")


def explain(user: Mapping[str, Any], kind: str, item: Mapping[str, Any], learner_view: bool) -> dict[str, Any]:
    """``{"steps": [...], "allowed": bool, "blocker": str}`` for one view."""
    steps: list[dict[str, Any]] = []
    roles = user_roles(user)
    steps.append(_step("帳號狀態", bool(user.get("active", True)), "帳號啟用中。" if user.get("active", True) else "帳號已停用。"))

    area, group = access.preferred_learning_scope(user)
    item_area, item_group = access.item_learning_scope(item)
    in_scope = (
        access.has_global_learning_access(user)
        or not access.has_explicit_learning_scope(user)
        or item_area == area
    )
    steps.append(_step(
        "角色與範圍", in_scope,
        f"角色：{('、'.join(roles) or '無')}；學習範圍：{area}／{group}；內容範圍：{item_area}／{item_group}。"
        + ("" if in_scope else " 內容不在此人的學習區域。"),
    ))

    course_id = _course_for(kind, item)
    gated = access.is_assignment_gated(user, learner_view)
    if course_id and gated:
        assigned = course_id in access.assigned_course_ids(user)
        steps.append(_step("課程指派", assigned, "已指派此課程。" if assigned else "此課程尚未指派給這位學員。"))
    else:
        steps.append(_step("課程指派", True, "此檢視不需指派即可看到。" if course_id else "內容不屬於任何課程。"))

    if course_id:
        try:
            from teacher_app.courses import repository as course_repository

            course = course_repository.get_course(course_id) if kind != "course" else dict(item)
        except Exception:
            course = None
        if course is None:
            steps.append(_step("課程狀態", False, "找不到所屬課程。"))
        else:
            published = bool(course.get("active", True)) and str(course.get("lifecycleStatus") or "published") == "published"
            steps.append(_step("課程狀態", published, "課程已發布。" if published else f"課程狀態為「{course.get('lifecycleStatus') or '停用'}」。"))

    if kind == "material":
        steps.append(_step("教材狀態", bool(item.get("active", True)), "教材啟用中。" if item.get("active", True) else "教材已停用。"))
    if kind == "exam":
        steps.append(_step("考卷狀態", bool(item.get("active", True)), "考卷啟用中。" if item.get("active", True) else "考卷已停用。"))
        window = _window_step(str(item.get("id") or ""))
        if window:
            steps.append(window)
        try:
            from teacher_app.learning import gate

            state = gate.exam_unlock_state(user, course_id)
            steps.append(_step("考卷解鎖", state["unlocked"], "必讀教材都已讀完。" if state["unlocked"] else state["reason"]))
        except Exception:
            pass

    if kind == "course":
        allowed = access.student_may_see_course(user, course_id, learner_view) and in_scope
    else:
        allowed = access.can_access_learning_item(user, item, learner_view)
        if kind == "exam":
            allowed = allowed and all(step["passed"] for step in steps if step["name"] in {"考卷狀態", "考試時間"})
    blocker = next((f"{step['name']}：{step['reason']}" for step in steps if not step["passed"]), "")
    if not allowed and not blocker:
        blocker = "學習範圍規則未放行（內容擁有組別與受眾設定）。"
    return {"steps": steps, "allowed": bool(allowed), "blocker": blocker}


def diagnose(user: Mapping[str, Any], kind: str, item: Mapping[str, Any]) -> dict[str, Any]:
    """Two columns: what the management pages show vs. what the reading area shows."""
    return {
        "management": explain(user, kind, item, learner_view=False),
        "learner": explain(user, kind, item, learner_view=True),
    }
