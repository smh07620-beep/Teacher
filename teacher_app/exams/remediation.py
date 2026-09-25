"""Pure learner remediation plan helpers for failed exams.

Remediation is derived from immutable exam evidence plus the current material
catalog.  It does not rewrite scores or delete failed attempts; it only tells
the learner what to review before starting a new attempt.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _material_projection(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": _text(item.get("id")),
        "title": _text(item.get("title") or item.get("filename") or "教材"),
        "materialType": _text(item.get("materialType") or "standard"),
        "currentVersion": max(1, _int(item.get("currentVersion"), 1)),
        "requiredCompletionVersion": max(
            1,
            _int(item.get("requiredCompletionVersion"), 1),
        ),
    }


def build_plan(
    *,
    score: Any,
    passing_score: Any,
    essay_count: Any,
    quiz_category_id: Any,
    course_id: Any,
    area: Any,
    group: Any,
    materials: Iterable[Mapping[str, Any]],
    max_materials: int = 6,
) -> dict[str, Any]:
    """Build a bounded same-scope review plan for an exam result.

    Essay-containing attempts are pending review and therefore never become a
    remediation task until a final score exists.  Passed attempts likewise do
    not create remediation work.
    """
    normalized_score = max(0, min(100, _int(score, 0)))
    normalized_passing = max(1, min(100, _int(passing_score, 80)))
    category_id = _text(quiz_category_id)
    linked_course = _text(course_id)
    normalized_area = _text(area) or "internal"
    normalized_group = _text(group) or "grpBio"
    pending_review = _int(essay_count, 0) > 0
    required = not pending_review and normalized_score < normalized_passing

    candidates: list[Mapping[str, Any]] = []
    if required:
        for material in materials:
            if not isinstance(material, Mapping) or not material.get("active", True):
                continue
            if _text(material.get("area")) != normalized_area:
                continue
            if _text(material.get("group")) != normalized_group:
                continue
            material_course = _text(material.get("courseId"))
            material_category = _text(material.get("category"))
            if linked_course:
                if material_course != linked_course:
                    continue
            elif category_id and material_category != category_id:
                continue
            candidates.append(material)

    candidates.sort(
        key=lambda item: (
            0 if _text(item.get("materialType")) == "sop" else 1,
            _text(item.get("title") or item.get("filename")),
        )
    )
    limit = max(1, min(20, _int(max_materials, 6)))
    review_materials = [_material_projection(item) for item in candidates[:limit]]
    gap = max(0, normalized_passing - normalized_score)

    return {
        "required": required,
        "pendingReview": pending_review,
        "score": normalized_score,
        "passingScore": normalized_passing,
        "scoreGap": gap if required else 0,
        "quizCategoryId": category_id,
        "courseId": linked_course,
        "area": normalized_area,
        "group": normalized_group,
        "reviewMaterials": review_materials,
        "reviewMaterialCount": len(review_materials),
        "reason": (
            "pending_review"
            if pending_review
            else "below_passing_score"
            if required
            else "passed"
        ),
    }


__all__ = ["build_plan"]
