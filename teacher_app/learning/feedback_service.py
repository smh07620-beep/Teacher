"""Learner course feedback policy and privacy boundary."""
from __future__ import annotations

import datetime as dt
from typing import Any, Mapping

from teacher_app.common.auth import has_role
from teacher_app.common.errors import ApiError
from teacher_app.courses import repository as course_repository
from teacher_app.learning import access as learning_access
from teacher_app.learning import feedback_repository


SUMMARY_ROLES = ("group_leader", "education_admin", "system_admin")


def _fail(code: str, message: str, status: int) -> ApiError:
    return ApiError(code, message, status=status)


def _username(user: Mapping[str, Any] | None) -> str:
    username = str((user or {}).get("username") or "").strip()
    if not username:
        raise _fail("AUTH_REQUIRED", "請先登入。", 401)
    return username


def _course_for_user(user: Mapping[str, Any] | None, course_id: str) -> dict:
    _username(user)
    course = course_repository.get_course(str(course_id or "").strip())
    if (
        not course
        or not course.get("active", True)
        or not learning_access.can_access_learning_item(user, course)
    ):
        raise _fail("COURSE_NOT_FOUND", "找不到可存取的課程。", 404)
    return course


def get_own_feedback(user: Mapping[str, Any] | None, course_id: str) -> dict:
    course = _course_for_user(user, course_id)
    username = _username(user)
    return {
        "courseId": course["id"],
        "courseTitle": str(course.get("title") or ""),
        "feedback": feedback_repository.get_feedback(course["id"], username),
    }


def submit_feedback(
    user: Mapping[str, Any] | None,
    course_id: str,
    payload: Mapping[str, Any] | None,
) -> dict:
    course = _course_for_user(user, course_id)
    username = _username(user)
    payload = payload or {}
    try:
        rating = int(payload.get("rating"))
    except (TypeError, ValueError):
        raise _fail("INVALID_COURSE_FEEDBACK_RATING", "回饋評分必須是 1 到 5。", 400)
    if rating not in {1, 2, 3, 4, 5}:
        raise _fail("INVALID_COURSE_FEEDBACK_RATING", "回饋評分必須是 1 到 5。", 400)
    comment = str(payload.get("comment") or "").strip()
    if len(comment) > 2000:
        raise _fail("COURSE_FEEDBACK_TOO_LONG", "回饋內容不可超過 2000 字。", 400)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    feedback = feedback_repository.upsert_feedback(
        course["id"],
        username,
        rating=rating,
        comment=comment,
        now=now,
    )
    return {
        "ok": True,
        "courseId": course["id"],
        "courseTitle": str(course.get("title") or ""),
        "feedback": feedback,
    }


def feedback_summary(user: Mapping[str, Any] | None, course_id: str) -> dict:
    course = _course_for_user(user, course_id)
    if not any(has_role(user, role) for role in SUMMARY_ROLES):
        raise _fail("COURSE_FEEDBACK_FORBIDDEN", "沒有權限查看課程回饋彙總。", 403)
    summary = feedback_repository.feedback_summary(course["id"])
    return {
        "courseId": course["id"],
        "courseTitle": str(course.get("title") or ""),
        **summary,
    }


__all__ = ["feedback_summary", "get_own_feedback", "submit_feedback"]
