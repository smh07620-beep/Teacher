"""Server-side exam unlock rule: required course materials must be completed first."""
from __future__ import annotations

import json
import os
from typing import Any, Mapping

from teacher_app.learning import access as learning_access
from teacher_app.learning import repository as learning_repository
from teacher_app.learning import versioning
from teacher_app.materials import repository as material_repository


def gate_enabled() -> bool:
    return os.environ.get("EXAM_GATE_ENABLED", "1").strip().lower() not in {"0", "false", "off", "no"}


def is_optional(material: Mapping[str, Any]) -> bool:
    meta = material.get("storageMeta") or {}
    return isinstance(meta, dict) and bool(meta.get("optional"))


def required_materials(course_id: str) -> list[dict]:
    if not course_id:
        return []
    try:
        materials = material_repository.list_uploaded_materials(include_inactive=False)
    except Exception:
        # An unreadable material list must not lock every learner out of exams.
        return []
    return [
        item
        for item in materials
        if str(item.get("courseId") or "") == course_id and not is_optional(item)
    ]


def _position(row: Mapping[str, Any]) -> dict:
    try:
        value = json.loads(row.get("position") or "{}")
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def course_progress(user: Mapping[str, Any], course_id: str) -> dict[str, Any]:
    """Per-material completion for the required materials of one course."""
    materials = required_materials(course_id)
    try:
        progress_rows = learning_repository.list_progress_for_user(str(user.get("username") or "").strip())
    except Exception:
        progress_rows = []
    rows = {str(row.get("material_id") or ""): row for row in progress_rows}
    done: list[str] = []
    missing: list[str] = []
    review_pages: dict[str, list[int]] = {}
    for item in materials:
        material_id = str(item.get("id") or "")
        row = rows.get(material_id)
        pages = [p for p in _position(row).get("reviewPages") or [] if isinstance(p, int)] if row else []
        ok = bool(
            row
            and row.get("completed")
            and versioning.completion_is_current(item, row.get("completed_version", 1))
            and not pages
        )
        (done if ok else missing).append(material_id)
        if pages:
            review_pages[material_id] = pages
    return {"materials": materials, "done": done, "missing": missing, "reviewPages": review_pages}


def exam_unlock_state(user: Mapping[str, Any], course_id: str) -> dict[str, Any]:
    """``{"unlocked", "progress", "missing", "reason"}`` for the exam(s) of a course."""
    if not gate_enabled() or not learning_access.is_assignment_gated(user):
        return {"unlocked": True, "progress": 100, "missing": [], "reason": ""}
    info = course_progress(user, course_id)
    total = len(info["materials"])
    if total == 0:
        return {"unlocked": True, "progress": 100, "missing": [], "reason": ""}
    progress = int(round(100 * len(info["done"]) / total))
    unlocked = not info["missing"]
    return {
        "unlocked": unlocked,
        "progress": progress,
        "missing": info["missing"],
        "reason": "" if unlocked else f"讀完教材後解鎖（目前 {progress}%）",
    }


def learner_bundle(user: Mapping[str, Any], course_id: str) -> dict[str, Any]:
    """Everything the course page needs in one response (progress, gate, exams)."""
    from teacher_app.assessments import repository as assessment_repository

    info = course_progress(user, course_id)
    rows = {}
    try:
        rows = {
            str(row.get("material_id") or ""): row
            for row in learning_repository.list_progress_for_user(str(user.get("username") or "").strip())
        }
    except Exception:
        rows = {}
    materials = []
    for item in info["materials"]:
        material_id = str(item.get("id") or "")
        row = rows.get(material_id) or {}
        materials.append({
            "id": material_id,
            "title": str(item.get("title") or item.get("filename") or ""),
            "progress": round(float(row.get("progress") or 0), 1),
            "completed": material_id in info["done"],
            "lastPage": int(_position(row).get("page") or 0) if row else 0,
            "reviewPages": info["reviewPages"].get(material_id, []),
        })
    state = exam_unlock_state(user, course_id)
    try:
        exams = [
            {
                "id": str(cat.get("id") or ""),
                "title": str(cat.get("title") or ""),
                "locked": not state["unlocked"],
            }
            for cat in assessment_repository.list_categories(None, None, False)
            if str(cat.get("courseId") or "") == course_id
        ]
    except Exception:
        exams = []
    checkpoints: dict[str, list] = {}
    try:
        from teacher_app.checkpoints import service as checkpoint_service

        for item in info["materials"]:
            if not learning_access.can_access_learning_item(user, item):
                continue
            found = checkpoint_service.learner_items(user, item)
            if found:
                checkpoints[str(item.get("id") or "")] = found
    except Exception:
        checkpoints = {}
    return {"courseId": course_id, "materials": materials, "gate": state, "exams": exams, "checkpoints": checkpoints}
