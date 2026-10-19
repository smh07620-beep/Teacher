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
from teacher_app.learning import repository as learning_repository
from teacher_app.learning import versioning
from teacher_app.materials import repository as material_repository


_POSTGRES_VERSION_COLUMN_PRESENT = False


def _postgres_has_completed_version_column(conn: Any) -> bool:
    """Ask information_schema once per process; the column never disappears once migrated."""
    global _POSTGRES_VERSION_COLUMN_PRESENT
    if _POSTGRES_VERSION_COLUMN_PRESENT:
        return True
    present = bool(
        conn.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema=current_schema() AND table_name=%s AND column_name=%s",
            ("material_progress", "completed_version"),
        ).fetchone()
    )
    _POSTGRES_VERSION_COLUMN_PRESENT = present
    return present


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
    # The UI, CSV export and per-exam grouping all read ``quizTitle``; without it
    # every record shows a blank exam and different exams collapse together.
    data["quizTitle"] = str(data.get("quiz_title", "") or "")
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
    from teacher_app.learning import gate as learning_gate
    from teacher_app.learning.routes import auto_tracked

    if learning_gate.gate_enabled() and auto_tracked(material) and learning_access.is_assignment_gated(user):
        # Slides, documents and media are completed by reading them in the reader,
        # so a button press must not show 已完成 while the exam stays locked.
        raise ProgressError("這份教材在閱讀器裡讀完後會自動完成，不需要手動標記。", 409)

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    completed_version = versioning.current_version(material)
    with common_db.transaction() as (conn, kind):
        if kind == "postgres":
            version_column = _postgres_has_completed_version_column(conn)
        else:
            version_column = any(
                str(dict(row).get("name", row[1] if len(row) > 1 else "")) == "completed_version"
                for row in conn.execute("PRAGMA table_info(material_progress)").fetchall()
            )
        if kind == "postgres":
            if version_column:
                conn.execute(
                    "INSERT INTO material_progress (emp_id,name,material_id,completed_at,completed_version) "
                    "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (emp_id,material_id) DO UPDATE SET "
                    "name=EXCLUDED.name, completed_at=EXCLUDED.completed_at, completed_version=EXCLUDED.completed_version",
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
            if version_column:
                conn.execute(
                    "INSERT INTO material_progress (emp_id,name,material_id,completed_at,completed_version) "
                    "VALUES (?,?,?,?,?) ON CONFLICT(emp_id,material_id) DO UPDATE SET "
                    "name=excluded.name, completed_at=excluded.completed_at, completed_version=excluded.completed_version",
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


def _has_assigned_course_in(user: Mapping[str, Any], area: str, group: str) -> bool:
    grants = list(learning_access.assigned_course_grants(user))
    if not grants:
        return False
    try:
        courses = course_repository.list_courses_by_ids(grants)
    except Exception:
        courses = []
    return any(
        scope.normalize_group(course.get("group")) == group
        and scope.normalize_area(course.get("area")) == area
        for course in courses
    )


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
    own_scope = learning_access.can_access_requested_scope(
        user,
        normalized_area,
        normalized_group,
    )
    if not own_scope:
        # A course assigned from another group is taken inside its owner group's
        # screen; that screen may ask for progress, but only about assigned courses.
        if not _has_assigned_course_in(user, normalized_area, normalized_group):
            raise ProgressError("此學習範圍不在你的授權範圍。", 403)

    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        progress_rows = conn.execute(
            f"SELECT * FROM material_progress WHERE emp_id={ph}",
            (emp_id,),
        ).fetchall()
        record_rows = conn.execute(
            f"SELECT * FROM exam_records WHERE emp_id={ph} AND training_area={ph} "
            f"ORDER BY created_at DESC",
            (emp_id, normalized_area),
        ).fetchall()
        all_records = [record_to_dict(row) for row in record_rows]

    # A course assigned from another group is taken (and recorded) under its
    # owner group; its records still belong in this learner's status.  Match by
    # course id OR by the exam (some older records carry no course id).
    granted_courses = set(learning_access.assigned_course_grants(user))
    granted_exam_ids: set[str] = set()
    if granted_courses:
        try:
            granted_exam_ids = {
                str(item.get("id") or "")
                for item in assessment_repository.list_categories(None, normalized_area, True)
                if str(item.get("courseId") or "") in granted_courses
            }
        except Exception:
            granted_exam_ids = set()
    records = [
        record
        for record in all_records
        if str(record.get("groupKey") or "") == normalized_group
        or str(record.get("courseId") or "") in granted_courses
        or str(record.get("quizCategoryId") or "") in granted_exam_ids
    ]

    try:
        smart_progress_rows = learning_repository.list_progress_for_user(
            str(user.get("username") or "").strip().lower()
        )
    except Exception:
        smart_progress_rows = []

    courses = course_repository.list_courses(
        normalized_area,
        normalized_group,
        False,
    )
    materials = [
        item
        for item in material_repository.list_uploaded_materials(include_inactive=False)
        if item.get("area") == normalized_area
        and (
            item.get("group") == normalized_group
            or str(item.get("courseId") or "") in granted_courses
        )
    ]
    allowed_material_ids = {
        str(item.get("id") or "") for item in materials if item.get("id")
    }
    legacy_valid_ids, legacy_stale_ids = versioning.valid_completed_material_ids(
        materials,
        progress_rows,
    )
    smart_completed_rows = [
        row for row in smart_progress_rows
        if bool(row.get("completed", False))
    ]
    smart_valid_ids, smart_stale_ids = versioning.valid_completed_material_ids(
        materials,
        smart_completed_rows,
    )
    valid_completed_ids = legacy_valid_ids | smart_valid_ids
    stale_completed_ids = (legacy_stale_ids | smart_stale_ids) - valid_completed_ids
    completed = {
        str(dict(row)["material_id"]): dict(row)["completed_at"]
        for row in progress_rows
        if str(dict(row).get("material_id") or "") in allowed_material_ids
        and str(dict(row).get("material_id") or "") in valid_completed_ids
    }
    for row in smart_completed_rows:
        material_id = str(row.get("material_id") or "")
        if material_id in allowed_material_ids and material_id in smart_valid_ids:
            completed[material_id] = str(
                row.get("completed_at")
                or row.get("last_viewed_at")
                or completed.get(material_id)
                or ""
            )
    categories = assessment_repository.list_categories(
        normalized_group,
        normalized_area,
        False,
    )
    if not own_scope:
        courses = [c for c in courses if str(c.get("id") or "") in granted_courses]
        categories = [c for c in categories if str(c.get("courseId") or "") in granted_courses]
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
        "materialsRetraining": sorted(stale_completed_ids & allowed_material_ids),
        "records": records,
    }


__all__ = [
    "ProgressError",
    "assessment_to_dict",
    "mark_material_complete",
    "my_progress",
    "record_to_dict",
]
