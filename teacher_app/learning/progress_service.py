"""Canonical legacy completion/progress projections used by learner surfaces."""
from __future__ import annotations

import datetime as dt
import json
from typing import Any, Mapping

from teacher_app.assessments import repository as assessment_repository
from teacher_app.common import db as common_db
from teacher_app.common import scope
from teacher_app.courses import repository as course_repository
from teacher_app.learning import access as learning_access
from teacher_app.materials import repository as material_repository
from teacher_app.materials import versioning as material_versioning


class ProgressError(ValueError):
    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.status = status


def _has_column(conn, kind: str, table: str, column: str) -> bool:
    """Compatibility probe for isolated legacy-schema tests and upgrade tools."""
    if kind == "postgres":
        row = conn.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema=current_schema() AND table_name=%s AND column_name=%s",
            (table, column),
        ).fetchone()
        return bool(row)
    return any(
        str(row[1]) == column
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    )


def record_to_dict(row: Mapping[str, Any] | Any) -> dict[str, Any]:
    data = dict(row)
    raw = data.pop("answers_detail", "[]")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = []
    data["answersDetail"] = raw
    data["timestamp"] = data.pop("created_at", "")
    data["empId"] = data.pop("emp_id", "")
    data["evaluatorName"] = data.pop("evaluator_name", "")
    data["evaluatorTitle"] = data.pop("evaluator_title", "")
    group = data.pop("group_key", scope.DEFAULT_GROUP) or scope.DEFAULT_GROUP
    data["groupKey"] = group
    data["groupLabel"] = scope.GROUPS.get(group, scope.GROUPS[scope.DEFAULT_GROUP])
    area = scope.normalize_area(data.pop("training_area", scope.DEFAULT_TRAINING_AREA))
    data["trainingArea"] = area
    data["trainingAreaLabel"] = scope.TRAINING_AREAS[area]
    data["courseId"] = data.pop("course_id", "") or ""
    data["reviewStatus"] = data.pop("review_status", "completed") or "completed"
    data["reviewedAt"] = data.pop("reviewed_at", "") or ""
    data["reviewerName"] = data.pop("reviewer_name", "") or ""
    data["reviewComment"] = data.pop("review_comment", "") or ""
    data["quizCategoryId"] = data.pop("quiz_category_id", "") or ""
    data["publicationId"] = data.pop("publication_id", "") or ""
    data["publicationHash"] = data.pop("publication_hash", "") or ""
    try:
        data["passingScore"] = max(1, min(100, int(data.pop("passing_score", 80) or 80)))
    except Exception:
        data["passingScore"] = 80
    return data


def assessment_to_dict(row: Mapping[str, Any] | Any) -> dict[str, Any]:
    data = dict(row)
    raw = data.pop("details", "{}") or "{}"
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}
    data["details"] = raw if isinstance(raw, dict) else {}
    data["assessmentType"] = data.pop("assessment_type", "")
    data["group"] = scope.normalize_group(data.pop("group_key", scope.DEFAULT_GROUP))
    data["empId"] = data.pop("emp_id", "")
    data["evaluatorName"] = data.pop("evaluator_name", "")
    data["evaluatorTitle"] = data.pop("evaluator_title", "")
    data["assessmentDate"] = data.pop("assessment_date", "")
    data["overallScore"] = float(data.pop("overall_score", 0) or 0)
    data["createdAt"] = data.pop("created_at", "")
    return data


def mark_material_complete(user: Mapping[str, Any], material_id: str) -> str:
    emp_id = user["empId"]
    name = user["name"]
    material_id = str(material_id or "").strip()[:100]
    if not emp_id or not name or not material_id:
        raise ProgressError("請先輸入姓名、工號，並指定教材", 400)
    material = material_repository.get_material(material_id)
    if not material:
        raise ProgressError("找不到教材", 404)
    if not learning_access.can_access_learning_item(user, material):
        raise ProgressError("此教材不在你的授權範圍。", 403)

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    completed_version = max(1, int(material.get("currentVersion") or 1))
    with common_db.transaction() as (conn, kind):
        versioned = _has_column(conn, kind, "material_progress", "completed_version")
        if kind == "postgres":
            if versioned:
                conn.execute(
                    "INSERT INTO material_progress (emp_id,name,material_id,completed_at,completed_version) "
                    "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (emp_id,material_id) DO UPDATE SET "
                    "name=EXCLUDED.name, completed_at=EXCLUDED.completed_at, "
                    "completed_version=EXCLUDED.completed_version",
                    (emp_id, name, material_id, now, completed_version),
                )
            else:
                conn.execute(
                    "INSERT INTO material_progress (emp_id,name,material_id,completed_at) "
                    "VALUES (%s,%s,%s,%s) ON CONFLICT (emp_id,material_id) DO UPDATE SET "
                    "name=EXCLUDED.name, completed_at=EXCLUDED.completed_at",
                    (emp_id, name, material_id, now),
                )
        else:
            if versioned:
                conn.execute(
                    "INSERT INTO material_progress (emp_id,name,material_id,completed_at,completed_version) "
                    "VALUES (?,?,?,?,?) ON CONFLICT(emp_id,material_id) DO UPDATE SET "
                    "name=excluded.name, completed_at=excluded.completed_at, "
                    "completed_version=excluded.completed_version",
                    (emp_id, name, material_id, now, completed_version),
                )
            else:
                conn.execute(
                    "INSERT INTO material_progress (emp_id,name,material_id,completed_at) "
                    "VALUES (?,?,?,?) ON CONFLICT(emp_id,material_id) DO UPDATE SET "
                    "name=excluded.name, completed_at=excluded.completed_at",
                    (emp_id, name, material_id, now),
                )
    return now


def my_progress(
    user: Mapping[str, Any],
    *,
    area: object = "pgy",
    group: object = scope.DEFAULT_GROUP,
) -> dict[str, Any]:
    emp_id = user["empId"]
    name = user["name"]
    if not emp_id or not name:
        raise ProgressError("請輸入姓名與工號", 400)

    normalized_area = scope.normalize_area(area)
    normalized_group = scope.normalize_group(group)
    if not learning_access.can_access_requested_scope(user, normalized_area, normalized_group):
        raise ProgressError("此學習範圍不在你的授權範圍。", 403)

    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        versioned = _has_column(conn, kind, "material_progress", "completed_version")
        fields = "material_id,completed_at,completed_version" if versioned else "material_id,completed_at"
        progress_rows = conn.execute(
            f"SELECT {fields} FROM material_progress WHERE emp_id={ph}",
            (emp_id,),
        ).fetchall()
        record_rows = conn.execute(
            f"SELECT * FROM exam_records WHERE emp_id={ph} AND training_area={ph} "
            f"AND group_key={ph} ORDER BY created_at DESC",
            (emp_id, normalized_area, normalized_group),
        ).fetchall()
        records = [record_to_dict(row) for row in record_rows]

    courses = course_repository.list_courses(normalized_area, normalized_group, False)
    materials = [
        item
        for item in material_repository.list_uploaded_materials(include_inactive=False)
        if item.get("area") == normalized_area and item.get("group") == normalized_group
    ]
    materials_by_id = {str(item.get("id") or ""): item for item in materials if item.get("id")}
    completed = {}
    for row in progress_rows:
        data = dict(row)
        material_id = str(data.get("material_id") or "")
        material = materials_by_id.get(material_id)
        if not material:
            continue
        completed_version = int(data.get("completed_version") or 1)
        if not material_versioning.completion_is_current(material, completed_version):
            continue
        completed[material_id] = data.get("completed_at")

    categories = assessment_repository.list_categories(normalized_group, normalized_area, False)
    result = []
    for course in courses:
        course_materials = [item for item in materials if item.get("courseId") == course["id"]]
        course_categories = [item for item in categories if item.get("courseId") == course["id"]]
        done = sum(1 for item in course_materials if item["id"] in completed)
        course_records = [record for record in records if record.get("courseId") == course["id"]]
        passed = any(
            record.get("reviewStatus") == "completed"
            and int(record.get("score", 0)) >= int(record.get("passingScore", 80) or 80)
            for record in course_records
        )
        has_exam = len(course_categories) > 0
        complete = (
            done == len(course_materials)
            and (passed if has_exam else True)
            and (len(course_materials) > 0 or has_exam)
        )
        result.append(
            {
                **course,
                "materialsTotal": len(course_materials),
                "materialsCompleted": done,
                "examRequired": has_exam,
                "examPassed": passed,
                "completed": complete,
            }
        )
    return {
        "scope": {"area": normalized_area, "group": normalized_group},
        "courses": result,
        "materialsCompleted": completed,
        "records": records,
    }


__all__ = [
    "ProgressError",
    "assessment_to_dict",
    "mark_material_complete",
    "my_progress",
    "record_to_dict",
]
