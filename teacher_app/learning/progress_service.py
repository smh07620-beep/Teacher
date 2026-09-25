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
from teacher_app.learning import completion as completion_rules
from teacher_app.materials import repository as material_repository


class ProgressError(ValueError):
    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.status = status


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
    area = scope.normalize_area(
        data.pop("training_area", scope.DEFAULT_TRAINING_AREA)
    )
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
        data["passingScore"] = max(
            1,
            min(100, int(data.pop("passing_score", 80) or 80)),
        )
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
    data["group"] = scope.normalize_group(
        data.pop("group_key", scope.DEFAULT_GROUP)
    )
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
    with common_db.transaction() as (conn, kind):
        if kind == "postgres":
            conn.execute(
                "INSERT INTO material_progress (emp_id,name,material_id,completed_at) "
                "VALUES (%s,%s,%s,%s) ON CONFLICT (emp_id,material_id) DO UPDATE SET "
                "name=EXCLUDED.name, completed_at=EXCLUDED.completed_at",
                (emp_id, name, material_id, now),
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
    if not learning_access.can_access_requested_scope(
        user,
        normalized_area,
        normalized_group,
    ):
        raise ProgressError("此學習範圍不在你的授權範圍。", 403)

    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        progress_rows = conn.execute(
            f"SELECT material_id,completed_at FROM material_progress WHERE emp_id={ph}",
            (emp_id,),
        ).fetchall()
        record_rows = conn.execute(
            f"SELECT * FROM exam_records WHERE emp_id={ph} AND training_area={ph} "
            f"AND group_key={ph} ORDER BY created_at DESC",
            (emp_id, normalized_area, normalized_group),
        ).fetchall()
        records = [record_to_dict(row) for row in record_rows]

    courses = course_repository.list_courses(
        normalized_area,
        normalized_group,
        False,
    )
    materials = [
        item
        for item in material_repository.list_uploaded_materials(include_inactive=False)
        if item.get("area") == normalized_area
        and item.get("group") == normalized_group
    ]
    allowed_material_ids = {
        str(item.get("id") or "") for item in materials if item.get("id")
    }
    completed = {
        str(dict(row)["material_id"]): dict(row)["completed_at"]
        for row in progress_rows
        if str(dict(row).get("material_id") or "") in allowed_material_ids
    }
    categories = assessment_repository.list_categories(
        normalized_group,
        normalized_area,
        False,
    )
    result = []
    for course in courses:
        course_materials = [
            item for item in materials if item.get("courseId") == course["id"]
        ]
        course_categories = [
            item for item in categories if item.get("courseId") == course["id"]
        ]
        course_records = [
            record for record in records if record.get("courseId") == course["id"]
        ]
        passed_exam_ids = {
            str(record.get("quizCategoryId") or "")
            for record in course_records
            if record.get("reviewStatus") == "completed"
            and int(record.get("score", 0))
            >= int(record.get("passingScore", 80) or 80)
        }
        completion = completion_rules.evaluate_course_completion(
            materials=course_materials,
            exams=course_categories,
            completed_material_ids=set(completed),
            passed_exam_ids=passed_exam_ids,
            policy=course.get("completionPolicy"),
        )
        result.append(
            {
                **course,
                **completion,
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
