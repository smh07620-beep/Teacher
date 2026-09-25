"""Canonical personalized dashboard projection over existing learning data."""
from __future__ import annotations

import datetime as dt
from typing import Any, Mapping

from teacher_app.assessments import repository as assessment_repository
from teacher_app.common import db as common_db
from teacher_app.common import scope
from teacher_app.courses import repository as course_repository
from teacher_app.learning import access as learning_access
from teacher_app.learning import assignment_service
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


def _parse_due(value: Any) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def dashboard_summary(
    user: Mapping[str, Any],
    *,
    today: str | None = None,
    now: dt.datetime | None = None,
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

    all_materials = [
        item
        for item in material_repository.list_uploaded_materials(include_inactive=False)
        if item.get("active", True)
    ]
    all_quizzes = [
        item
        for item in assessment_repository.list_categories(None, None, False)
        if item.get("active", True)
    ]
    all_courses = course_repository.list_courses(None, None, False)

    assignments = assignment_service.list_for_user(user)
    assignment_mode = bool(assignments)
    assigned_course_ids = {
        str(item.get("courseId") or "") for item in assignments if item.get("courseId")
    }
    required_course_ids = {
        str(item.get("courseId") or "")
        for item in assignments
        if item.get("courseId") and item.get("required", True)
    }

    if assignment_mode:
        courses = [
            item for item in all_courses if str(item.get("id") or "") in assigned_course_ids
        ]
        materials = [
            item
            for item in all_materials
            if str(item.get("courseId") or "") in required_course_ids
        ]
        quizzes = [
            item
            for item in all_quizzes
            if str(item.get("courseId") or "") in required_course_ids
        ]
        records = [
            record
            for record in all_records
            if str(record.get("courseId") or "") in assigned_course_ids
        ]
    else:
        materials = [
            item
            for item in all_materials
            if learning_access.can_access_learning_item(user, item)
        ]
        quizzes = [
            item
            for item in all_quizzes
            if learning_access.can_access_learning_item(user, item)
        ]
        courses = [
            item
            for item in all_courses
            if learning_access.can_access_learning_item(user, item)
        ]
        records = [
            record for record in all_records if _record_visible_to_user(user, record)
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

    current_time = now or dt.datetime.now(dt.timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=dt.timezone.utc)
    current_time = current_time.astimezone(dt.timezone.utc)
    assignment_rows = []
    course_by_id = {
        str(course.get("id") or ""): course for course in all_courses if course.get("id")
    }
    all_materials_by_course: dict[str, list[dict]] = {}
    all_quizzes_by_course: dict[str, list[dict]] = {}
    for material in all_materials:
        all_materials_by_course.setdefault(str(material.get("courseId") or ""), []).append(material)
    for quiz in all_quizzes:
        all_quizzes_by_course.setdefault(str(quiz.get("courseId") or ""), []).append(quiz)

    for assignment in assignments:
        course_id = str(assignment.get("courseId") or "")
        course = course_by_id.get(course_id, {})
        course_materials = all_materials_by_course.get(course_id, [])
        course_quizzes = all_quizzes_by_course.get(course_id, [])
        materials_completed = sum(
            1 for material in course_materials if str(material.get("id") or "") in completed_material_ids
        )
        quiz_ids = {str(quiz.get("id") or "") for quiz in course_quizzes if quiz.get("id")}
        exam_passed = bool(quiz_ids & passed_quiz_ids) if quiz_ids else True
        completed = (
            materials_completed == len(course_materials)
            and exam_passed
            and bool(course_materials or course_quizzes)
        )
        due = _parse_due(assignment.get("dueAt"))
        assignment_rows.append(
            {
                **assignment,
                "courseTitle": str(course.get("title") or "未命名課程"),
                "materialsTotal": len(course_materials),
                "materialsCompleted": materials_completed,
                "examRequired": bool(course_quizzes),
                "examPassed": exam_passed,
                "completed": completed,
                "overdue": bool(due and due < current_time and not completed),
            }
        )

    preferred_area, preferred_group = learning_access.preferred_learning_scope(user)
    overdue_count = sum(1 for item in assignment_rows if item.get("overdue"))
    required_pending = sum(
        1
        for item in assignment_rows
        if item.get("required", True) and not item.get("completed")
    )
    pending_courses = [
        {
            "id": str(item.get("courseId") or ""),
            "title": str(item.get("courseTitle") or "未命名課程"),
            "area": str(item.get("area") or preferred_area),
            "group": str(item.get("group") or preferred_group),
            "dueAt": str(item.get("dueAt") or ""),
            "overdue": bool(item.get("overdue")),
            "materialsCompleted": int(item.get("materialsCompleted") or 0),
            "materialsTotal": int(item.get("materialsTotal") or 0),
            "examRequired": bool(item.get("examRequired")),
            "examPassed": bool(item.get("examPassed")),
        }
        for item in assignment_rows
        if item.get("required", True) and not item.get("completed")
    ]
    pending_courses.sort(
        key=lambda item: (
            0 if item.get("overdue") else 1,
            str(item.get("dueAt") or "9999-12-31"),
            str(item.get("title") or ""),
        )
    )
    required_assignments = sum(
        1 for item in assignment_rows if item.get("required", True)
    )

    return {
        "empId": emp_id,
        "name": display_name,
        "scope": {"area": preferred_area, "group": preferred_group},
        "scopeSource": "assignments" if assignment_mode else "profile",
        "assignmentMode": assignment_mode,
        "assignments": assignment_rows,
        "assignmentsTotal": len(assignment_rows),
        "assignmentsOverdue": overdue_count,
        "requiredAssignmentsPending": required_pending,
        "requiredAssignments": required_assignments,
        "overdueAssignments": overdue_count,
        "activeCourses": len(active_courses),
        "materialsTotal": len(active_material_ids),
        "materialsCompleted": material_done,
        "materialsPending": max(0, len(active_material_ids) - material_done),
        "examsTotal": len(active_quiz_ids),
        "examsPassed": quiz_done,
        "examsPending": max(0, len(active_quiz_ids) - quiz_done),
        "pendingExams": pending_exams[:5],
        "pendingCourses": pending_courses[:5],
        "essayReviewsPending": pending_review_count,
        "teacherAssessmentsCompleted": len(assessments),
        "progressPercent": progress_percent,
        "latestExam": records[0] if records else None,
        "latestAssessment": assessments[0] if assessments else None,
    }


__all__ = ["dashboard_summary"]
