"""Pure course-completion rules shared by learner projections.

The first rule generation deliberately preserves the historical behavior:
all active course materials are required and, when exams exist, passing any one
linked exam satisfies the exam requirement.  A normalized policy shape is
accepted now so a later schema migration can persist explicit course rules
without creating a second completion implementation.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence


EXAM_MODES = {"any", "all", "none"}


def normalize_policy(value: Any) -> dict[str, Any]:
    data = value if isinstance(value, Mapping) else {}
    material_ids = data.get("requiredMaterialIds")
    exam_ids = data.get("requiredExamIds")
    mode = str(data.get("examMode") or "any").strip().lower()
    if mode not in EXAM_MODES:
        mode = "any"
    return {
        "requiredMaterialIds": [
            str(item).strip()
            for item in material_ids
            if str(item).strip()
        ] if isinstance(material_ids, list) else [],
        "requiredExamIds": [
            str(item).strip()
            for item in exam_ids
            if str(item).strip()
        ] if isinstance(exam_ids, list) else [],
        "examMode": mode,
    }


def evaluate_course_completion(
    *,
    materials: Sequence[Mapping[str, Any]],
    exams: Sequence[Mapping[str, Any]],
    completed_material_ids: set[str] | Sequence[str],
    passed_exam_ids: set[str] | Sequence[str],
    policy: Any = None,
) -> dict[str, Any]:
    rules = normalize_policy(policy)
    material_by_id = {
        str(item.get("id") or ""): item
        for item in materials
        if str(item.get("id") or "")
    }
    exam_by_id = {
        str(item.get("id") or ""): item
        for item in exams
        if str(item.get("id") or "")
    }

    configured_materials = rules["requiredMaterialIds"]
    required_material_ids = (
        {item for item in configured_materials if item in material_by_id}
        if configured_materials
        else set(material_by_id)
    )
    configured_exams = rules["requiredExamIds"]
    required_exam_ids = (
        {item for item in configured_exams if item in exam_by_id}
        if configured_exams
        else set(exam_by_id)
    )

    completed_ids = {str(item) for item in completed_material_ids}
    passed_ids = {str(item) for item in passed_exam_ids}
    material_done_ids = required_material_ids & completed_ids
    materials_complete = required_material_ids <= completed_ids

    exam_mode = rules["examMode"]
    if exam_mode == "none" or not required_exam_ids:
        exam_required = False
        exams_complete = True
    elif exam_mode == "all":
        exam_required = True
        exams_complete = required_exam_ids <= passed_ids
    else:
        exam_required = True
        exams_complete = bool(required_exam_ids & passed_ids)

    has_requirements = bool(required_material_ids or (exam_required and required_exam_ids))
    return {
        "completed": bool(has_requirements and materials_complete and exams_complete),
        "materialsTotal": len(required_material_ids),
        "materialsCompleted": len(material_done_ids),
        "materialsComplete": materials_complete,
        "examRequired": exam_required,
        "examPassed": exams_complete,
        "requiredMaterialIds": sorted(required_material_ids),
        "requiredExamIds": sorted(required_exam_ids),
        "examMode": exam_mode,
    }


__all__ = ["EXAM_MODES", "evaluate_course_completion", "normalize_policy"]
