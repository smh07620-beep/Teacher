"""Learner-facing course visibility that matches material visibility.

``/api/slides`` already hides a material from accounts outside its owning group
unless the teacher shared it (``audience_scope``).  ``/api/courses`` used to list
every course of the requested group, so an account that could not see any of a
course's materials still got an empty course shell.

A course is now shown to a learner only when at least one of these holds:

* the learner may see the course through their own area/group (owner scope);
* the learner may see at least one active material of that course (shared in).

Cross-group managers and legacy scope-less fixtures keep seeing everything, like
they do for materials.  This only affects what the learner list returns; it is
presentation of data the server already scopes, never a grant of new access.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping

from teacher_app.learning import access as learning_access


def _default_materials() -> list[dict]:
    from teacher_app.materials import repository as material_repository

    return material_repository.list_uploaded_materials(include_inactive=False)


def _default_meta(ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    from teacher_app.common import content_audience

    return content_audience._material_meta(ids)


def _sees_everything(user: Mapping[str, Any]) -> bool:
    from teacher_app.common import content_audience

    return (
        learning_access.has_global_learning_access(user)
        or content_audience._cross_group_manager(user)
        or not learning_access.has_explicit_learning_scope(user)
    )


def filter_courses_for_user(
    user: Mapping[str, Any] | None,
    courses: list[dict],
    *,
    material_loader: Callable[[], list[dict]] | None = None,
    meta_loader: Callable[[Iterable[str]], dict[str, dict[str, Any]]] | None = None,
) -> list[dict]:
    if not user:
        return []
    if not courses or _sees_everything(user):
        return list(courses)

    own = [c for c in courses if learning_access.can_access_learning_item(user, c)]
    if len(own) == len(courses):
        return list(courses)

    wanted = {str(c.get("id") or "") for c in courses} - {str(c.get("id") or "") for c in own}
    materials = [
        m for m in (material_loader or _default_materials)()
        if str(m.get("courseId") or "") in wanted
    ]
    meta_map = (meta_loader or _default_meta)([str(m.get("id") or "") for m in materials])

    shared_course_ids: set[str] = set()
    for material in materials:
        meta = meta_map.get(str(material.get("id") or ""))
        if not meta:
            continue
        candidate = {**material, **meta, "group": meta.get("ownerGroup") or material.get("group")}
        if learning_access.can_access_learning_item(user, candidate):
            shared_course_ids.add(str(material.get("courseId") or ""))

    own_ids = {str(c.get("id") or "") for c in own}
    return [c for c in courses if str(c.get("id") or "") in own_ids | shared_course_ids]


def add_personally_assigned_courses(
    user: Mapping[str, Any] | None,
    courses: list[dict],
    *,
    course_loader: Callable[[str], dict | None] | None = None,
) -> list[dict]:
    """Append courses from other groups that this person was individually assigned.

    The learner course list is requested per group, so a course owned by another
    group would never show up even though an administrator assigned it to the
    person.  Only ids in ``personal_course_grants`` (published, same area) are added.
    """
    if not user:
        return list(courses)
    grants = learning_access.personal_course_grants(user)
    if not grants:
        return list(courses)
    if course_loader is None:
        from teacher_app.courses import repository as course_repository

        course_loader = course_repository.get_course
    present = {str(c.get("id") or "") for c in courses}
    extra = []
    for course_id in sorted(grants - present):
        course = course_loader(course_id)
        if course:
            extra.append({**course, "assignedFromGroup": course.get("group", "")})
    return list(courses) + extra


def add_personally_assigned_exams(
    user: Mapping[str, Any] | None,
    categories: list[dict],
    all_categories_loader: Callable[[], list[dict]],
) -> list[dict]:
    """Append exams (quiz categories) linked to a course this person was individually assigned.

    Same grant as ``add_personally_assigned_courses``: the exam must hang under a
    granted course; nothing else from the other group becomes visible.
    """
    if not user:
        return list(categories)
    grants = learning_access.personal_course_grants(user)
    if not grants:
        return list(categories)
    present = {str(c.get("id") or "") for c in categories}
    extra = [
        {**item, "assignedFromGroup": item.get("group", "")}
        for item in all_categories_loader()
        if str(item.get("courseId") or "") in grants and str(item.get("id") or "") not in present
    ]
    return list(categories) + extra


__all__ = ["add_personally_assigned_courses", "add_personally_assigned_exams", "filter_courses_for_user"]
