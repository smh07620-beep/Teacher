"""Canonical personalized dashboard projection over existing learning data."""
from __future__ import annotations

import datetime as dt
from typing import Any, Mapping

from teacher_app.assessments import repository as assessment_repository
from teacher_app.common import db as common_db
from teacher_app.common import scope
from teacher_app.courses import repository as course_repository
from teacher_app.learning import access as learning_access
from teacher_app.learning.progress_service import assessment_to_dict, record_to_dict
from teacher_app.materials import repository as material_repository


def _record_visible_to_user(user: Mapping[str, Any], record: Mapping[str, Any]) -> bool:
    return learning_access.can_access_learning_item(
        user,
        {
            "area": record.get("trainingArea"),
            "group": record.get("groupKey"),
        },
    )


def dashboard_summary(
    user: Mapping[str, Any],
    *,
    today: str | None = None,
) -> dict[str, Any]:
    emp_id = user["empId"]
    requested_name = user["name"]

    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        progress_rows = conn.execute(
            f"SELECT material_id,name,completed_at FROM material_progress "
            f"WHERE emp_id={ph} ORDER BY completed_at DESC",
            (emp_id,),
        ).fetchall()
        record_rows = conn.execute(
            f"SELECT * FROM exam_records WHERE emp_id={ph} ORDER BY created_at DESC",
            (emp_id,),
        ).fetchall()
        assessment_rows = conn.execute(
            f"SELECT * FROM pgy_assessments WHERE emp_id={ph} ORDER BY created_at DESC",
            (emp_id,),
        ).fetchall()

    all_records = [record_to_dict(row) for row in record_rows]
    records = [record for record in all_records if _record_visible_to_user(user, record)]
    assessments = [assessment_to_dict(row) for row in assessment_rows]
    completed_material_ids = {
        str(dict(row).get("material_id", ""))
        for row in progress_rows
        if dict(row).get("material_id")
    }

    display_name = requested_name
    if not display_name:
        for row in list(progress_rows) + list(record_rows) + list(assessment_rows):
            candidate = str(dict(row).get("name", "") or "").strip()
            if candidate:
                display_name = candidate[:100]
                break

    materials = [
        item
        for item in material_repository.list_uploaded_materials(include_inactive=False)
        if item.get("active", True)
        and learning_access.can_access_learning_item(user, item)
    ]
    quizzes = [
        item
        for item in assessment_repository.list_categories(None, None, False)
        if item.get("active", True)
        and learning_access.can_access_learning_item(user, item)
    ]
    courses = [
        item
        for item in course_repository.list_courses(None, None, False)
        if learning_access.can_access_learning_item(user, item)
    ]
    active_material_ids = {
        str(item.get("id", "")) for item in materials if item.get("id")
    }
    material_done = len(active_material_ids & completed_material_ids)

    passed_quiz_ids = set()
    pending_review_count = 0
    for record in records:
        if record.get("reviewStatus") == "pending":
            pending_review_count += 1
            continue
        quiz_id = str(record.get("quizCategoryId", "") or "")
        if not quiz_id:
            continue
        try:
            if float(record.get("score", 0) or 0) >= float(
                record.get("passingScore", 80) or 80
            ):
                passed_quiz_ids.add(quiz_id)
        except (TypeError, ValueError):
            pass
    active_quiz_ids = {
        str(item.get("id", "")) for item in quizzes if item.get("id")
    }
    quiz_done = len(active_quiz_ids & passed_quiz_ids)

    total_required = len(active_material_ids) + len(active_quiz_ids)
    total_done = material_done + quiz_done
    progress_percent = round(total_done / total_required * 100) if total_required else 0

    current_day = today or dt.date.today().isoformat()
    active_courses = []
    for course in courses:
        start = str(course.get("startDate", "") or "")[:10]
        end = str(course.get("endDate", "") or "")[:10]
        if (not start or start <= current_day) and (not end or end >= current_day):
            active_courses.append(course)

    pending_exams = []
    for quiz in quizzes:
        quiz_id = str(quiz.get("id", "") or "")
        if not quiz_id or quiz_id in passed_quiz_ids:
            continue
        pending_exams.append(
            {
                "id": quiz_id,
                "title": str(quiz.get("title", "") or "未命名考核"),
                "area": str(quiz.get("area", "internal") or "internal"),
                "group": str(
                    quiz.get("group", scope.DEFAULT_GROUP) or scope.DEFAULT_GROUP
                ),
                "courseId": str(quiz.get("courseId", "") or ""),
                "passingScore": int(quiz.get("passingScore", 80) or 80),
                "publishedAt": str(
                    quiz.get("publishedAt", "") or quiz.get("dateAdded", "") or ""
                ),
            }
        )
    pending_exams.sort(key=lambda item: item.get("publishedAt", ""), reverse=True)
    preferred_area, preferred_group = learning_access.preferred_learning_scope(user)

    return {
        "empId": emp_id,
        "name": display_name,
        "scope": {"area": preferred_area, "group": preferred_group},
        "activeCourses": len(active_courses),
        "materialsTotal": len(active_material_ids),
        "materialsCompleted": material_done,
        "materialsPending": max(0, len(active_material_ids) - material_done),
        "examsTotal": len(active_quiz_ids),
        "examsPassed": quiz_done,
        "examsPending": max(0, len(active_quiz_ids) - quiz_done),
        "pendingExams": pending_exams[:5],
        "essayReviewsPending": pending_review_count,
        "teacherAssessmentsCompleted": len(assessments),
        "progressPercent": progress_percent,
        "latestExam": records[0] if records else None,
        "latestAssessment": assessments[0] if assessments else None,
    }


__all__ = ["dashboard_summary"]
