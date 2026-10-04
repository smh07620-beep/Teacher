"""F6 material-version change impact analysis."""
from __future__ import annotations

from typing import Any, Mapping

from teacher_app.assessments import repository as assessment_repository
from teacher_app.auth import accounts
from teacher_app.common import db as common_db
from teacher_app.learning import assignment_service
from teacher_app.materials import (
    ai_presentation_repository,
    derivative_repository,
    repository as material_repository,
)


def _completed_learner_count(material_id: str) -> int:
    usernames: set[str] = set()
    emp_ids: set[str] = set()
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        try:
            rows = conn.execute(
                f"SELECT username FROM learning_progress WHERE material_id={ph} AND completed="
                + ("TRUE" if kind == "postgres" else "1"),
                (material_id,),
            ).fetchall()
            usernames.update(
                str(dict(row).get("username") or "").strip().lower()
                for row in rows
                if str(dict(row).get("username") or "").strip()
            )
        except Exception:
            pass
        try:
            rows = conn.execute(
                f"SELECT emp_id FROM material_progress WHERE material_id={ph}",
                (material_id,),
            ).fetchall()
            emp_ids.update(
                str(dict(row).get("emp_id") or "").strip()
                for row in rows
                if str(dict(row).get("emp_id") or "").strip()
            )
        except Exception:
            pass

    if not emp_ids:
        return len(usernames)
    account_map = {
        str(item.get("empId") or "").strip(): str(item.get("username") or "").strip().lower()
        for item in accounts.list_accounts()
        if str(item.get("empId") or "").strip()
    }
    for emp_id in emp_ids:
        username = account_map.get(emp_id)
        if username:
            usernames.add(username)
        else:
            usernames.add("emp:" + emp_id)
    return len(usernames)


def analyze_material_change(
    actor: Mapping[str, Any] | None,
    material_id: str,
    *,
    proposed_version: int | None = None,
    requires_retraining: bool = False,
) -> dict:
    material = material_repository.get_material(str(material_id or ""))
    if not material:
        raise ValueError("找不到教材。")

    current_version = max(1, int(material.get("currentVersion") or 1))
    next_version = max(current_version + 1, int(proposed_version or current_version + 1))
    course_id = str(material.get("courseId") or "")

    questions = []
    for raw in assessment_repository.list_bank_questions():
        source_id = str(raw.get("source_material_id") or raw.get("sourceMaterialId") or "")
        if source_id == material_id:
            questions.append(dict(raw))

    category_ids = {
        str(item.get("quiz_category_id") or item.get("quizCategoryId") or "")
        for item in questions
        if str(item.get("quiz_category_id") or item.get("quizCategoryId") or "")
    }
    categories = {
        str(item.get("id") or ""): item
        for item in assessment_repository.list_categories(include_inactive=True)
    }
    impacted_exams = [categories[cid] for cid in sorted(category_ids) if cid in categories]
    published_exams = [item for item in impacted_exams if item.get("active", False)]

    presentations = ai_presentation_repository.list_presentations(
        material_id=material_id,
        limit=100,
    )
    derivatives = derivative_repository.list_for_material(material_id)
    ppt_derivatives = [item for item in derivatives if item.get("type") == "presentation"]
    video_derivatives = [item for item in derivatives if item.get("type") == "video"]
    stale_derivatives = [
        item for item in derivatives
        if int(item.get("materialVersion") or 0) < current_version
    ]

    assignments = []
    if actor and course_id:
        try:
            assignments = [
                item for item in assignment_service.admin_list(actor, include_inactive=False)
                if str(item.get("courseId") or "") == course_id
            ]
        except Exception:
            assignments = []

    completed_learners = _completed_learner_count(material_id)

    recommendations = []
    if questions:
        recommendations.append({
            "kind": "questions",
            "severity": "high" if published_exams else "medium",
            "label": f"重新審查 {len(questions)} 題來源考題",
            "reason": "考題來源教材即將改版；歷史考卷 snapshot 保留，但新考卷前應重新確認內容。",
        })
    if ppt_derivatives:
        recommendations.append({
            "kind": "presentation",
            "severity": "medium",
            "label": f"檢查／重產 {len(ppt_derivatives)} 份已發布 AI PowerPoint",
            "reason": "既有簡報仍綁定舊教材版本，不會被靜默改寫。",
        })
    if video_derivatives:
        recommendations.append({
            "kind": "video",
            "severity": "medium",
            "label": f"檢查／重產 {len(video_derivatives)} 支 AI 教學影片",
            "reason": "影片來源 PowerPoint 與教材版本會保留，可由教師決定是否重產。",
        })
    if requires_retraining and completed_learners:
        recommendations.append({
            "kind": "retraining",
            "severity": "high",
            "label": f"要求 {completed_learners} 位既有完成學員重新訓練",
            "reason": "本次版本被標記為重大變更；歷史完成證據保留。",
        })

    return {
        "material": {
            "id": str(material.get("id") or material_id),
            "title": str(material.get("title") or ""),
            "courseId": course_id,
            "area": str(material.get("area") or ""),
            "group": str(material.get("group") or ""),
            "currentVersion": current_version,
            "proposedVersion": next_version,
        },
        "requiresRetraining": bool(requires_retraining),
        "summary": {
            "linkedCourse": 1 if course_id else 0,
            "activeAssignments": len(assignments),
            "completedLearners": completed_learners,
            "sourceQuestions": len(questions),
            "impactedExams": len(impacted_exams),
            "publishedExams": len(published_exams),
            "presentationRevisions": len(presentations),
            "publishedPresentations": len(ppt_derivatives),
            "publishedVideos": len(video_derivatives),
            "alreadyStaleDerivatives": len(stale_derivatives),
        },
        "questions": [
            {
                "id": str(item.get("id") or ""),
                "categoryId": str(item.get("quiz_category_id") or item.get("quizCategoryId") or ""),
                "status": str(item.get("status") or ""),
                "version": int(item.get("version") or 1),
                "question": str(item.get("question") or "")[:180],
            }
            for item in questions[:100]
        ],
        "exams": [
            {
                "id": str(item.get("id") or ""),
                "title": str(item.get("title") or ""),
                "published": bool(item.get("active", False)),
                "reviewStatus": str(item.get("reviewStatus") or item.get("review_status") or ""),
            }
            for item in impacted_exams
        ],
        "derivatives": [
            {
                "id": str(item.get("derivativeId") or ""),
                "type": str(item.get("type") or ""),
                "materialVersion": int(item.get("materialVersion") or 1),
                "publishedAt": str(item.get("publishedAt") or ""),
                "willRequireReview": True,
            }
            for item in derivatives
        ],
        "recommendations": recommendations,
        "decision": {
            "questionReviewRequired": bool(questions),
            "derivativeReviewRequired": bool(derivatives),
            "retrainingAffectedLearners": completed_learners if requires_retraining else 0,
            "historicEvidencePreserved": True,
        },
    }


__all__ = ["analyze_material_change"]
