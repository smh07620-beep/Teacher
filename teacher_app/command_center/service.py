"""Read-only aggregation for Teacher 7.1 Training Command Center.

The command center is the single read projection for learner/teacher work that
needs attention. Canonical domain stores remain authoritative; this module does
not duplicate mutation workflows or authorization decisions.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Mapping, Optional

from teacher_app.command_center import audience, dashboard_service
from teacher_app.common.auth import has_permission, normalize_role
from teacher_app.common.errors import ApiError
from teacher_app.courses import repository as course_repository
from teacher_app.exams import records as exam_records
from teacher_app.learning import access as learning_access
from teacher_app.learning import assignment_service
from teacher_app.learning import intervention_service
from teacher_app.pgy import service as pgy_service
from teacher_app.worker import repository as worker_repository


LOGGER = logging.getLogger(__name__)


ACTIONABLE_PGY = {
    "student": {
        "assigned": ("submit", "填寫並送出"),
    },
    "clinical_teacher": {
        "submitted": ("teacher_sign", "教師簽核"),
    },
    "group_leader": {
        "teacher_signed": ("group_countersign", "組長複核"),
    },
    "education_admin": {
        "group_countersigned": ("finalize", "最終確認"),
    },
}

STATUS_LABELS = {
    "assigned": "待學員完成",
    "submitted": "待教師簽核",
    "teacher_signed": "待組長複核",
    "group_countersigned": "待最終確認",
}

TEACHER_DUE_WINDOW = dt.timedelta(days=7)


def _parse_datetime(value: Any) -> Optional[dt.datetime]:
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


def _is_overdue(value: Any, now: dt.datetime) -> bool:
    due = _parse_datetime(value)
    return bool(due and due < now)


def _task_sort_key(item: Mapping[str, Any]):
    priority = {
        "review": 0,
        "material_failure": 1,
        "intervention": 2,
        "retraining": 3,
        "course": 4,
        "exam": 5,
        "material": 6,
        "due": 7,
        "draft": 8,
    }.get(str(item.get("kind") or ""), 8)
    due = _parse_datetime(item.get("dueAt"))
    return (
        0 if item.get("overdue") else 1,
        0 if item.get("interventionId") else 1,
        priority,
        due or dt.datetime.max.replace(tzinfo=dt.timezone.utc),
        str(item.get("title") or ""),
    )


def _visible_to_teacher(user: Mapping[str, Any], item: Mapping[str, Any]) -> bool:
    try:
        return learning_access.can_access_learning_item(user, item)
    except Exception:
        return False


def _has_learner_persona(user: Mapping[str, Any], role: str) -> bool:
    if role == "student":
        return True
    raw_roles = user.get("roles") or []
    if isinstance(raw_roles, str):
        raw_roles = [raw_roles]
    return any(normalize_role(value) == "student" for value in raw_roles)


def _learner_action_items(user: Mapping[str, Any], current: dt.datetime) -> list[dict[str, Any]]:
    """Project canonical dashboard learning state into one learner task list."""
    try:
        dashboard = dashboard_service.dashboard_summary(user, now=current)
    except Exception as exc:
        LOGGER.warning(
            "command center learner projection failed error_type=%s",
            type(exc).__name__,
        )
        return []

    values: list[dict[str, Any]] = []
    pending_courses = list(dashboard.get("pendingCourses") or [])
    pending_course_ids = {str(item.get("id") or "") for item in pending_courses}

    for course in pending_courses:
        course_id = str(course.get("id") or "")
        next_kind = str(course.get("nextKind") or "")
        resume_material_id = str(course.get("resumeMaterialId") or "")
        resume_exam_id = str(course.get("resumeExamId") or "")
        resume_progress = max(0, min(100, int(float(course.get("resumeProgress") or 0))))
        target = "exam" if next_kind == "exam" and resume_exam_id else "materials"
        resource_id = resume_exam_id if target == "exam" else course_id
        if next_kind == "retraining":
            action_label = "重新閱讀新版"
        elif next_kind == "material" and resume_progress > 0:
            action_label = f"繼續閱讀 {resume_progress}%"
        elif next_kind == "material":
            action_label = "開始閱讀"
        elif target == "exam":
            action_label = "開始考核"
        else:
            action_label = "繼續學習"
        values.append({
            "id": str(course.get("assignmentId") or course_id),
            "resourceId": resource_id,
            "courseId": course_id,
            "materialId": resume_material_id,
            "resumeProgress": resume_progress,
            "persona": "learner",
            "domain": "learning",
            "kind": "course",
            "title": str(course.get("title") or "待完成課程"),
            "status": "overdue" if course.get("overdue") else "pending",
            "statusLabel": "已逾期" if course.get("overdue") else "待完成課程",
            "group": str(course.get("group") or ""),
            "area": str(course.get("area") or "internal"),
            "dueAt": str(course.get("dueAt") or ""),
            "overdue": bool(course.get("overdue")),
            "detail": (
                f"教材 {int(course.get('materialsCompleted') or 0)}/{int(course.get('materialsTotal') or 0)}"
                + (" · 考核已通過" if course.get("examRequired") and course.get("examPassed") else " · 尚待考核" if course.get("examRequired") else "")
            ),
            "action": "course",
            "actionLabel": action_label,
            "target": target,
        })

    for material in list(dashboard.get("pendingMaterials") or []):
        material_id = str(material.get("id") or "")
        course_id = str(material.get("courseId") or "")
        retraining = bool(material.get("retrainingRequired"))
        if course_id in pending_course_ids and not retraining:
            continue
        values.append({
            "id": material_id,
            "resourceId": material_id,
            "courseId": course_id,
            "persona": "learner",
            "domain": "learning",
            "kind": "retraining" if retraining else "material",
            "title": str(material.get("title") or "待完成教材"),
            "status": "retraining" if retraining else "pending",
            "statusLabel": "需重新訓練" if retraining else "待完成教材",
            "group": str(material.get("group") or ""),
            "area": str(material.get("area") or "internal"),
            "dueAt": "",
            "overdue": False,
            "detail": (
                "教材或 SOP 已更新重大版本，請完成最新版。"
                if retraining
                else (
                    f"已閱讀 {int(float(material.get('progress') or 0))}%"
                    if float(material.get("progress") or 0) > 0
                    else "此教材尚未完成。"
                )
            ),
            "progress": float(material.get("progress") or 0),
            "action": "material",
            "actionLabel": (
                "重新學習"
                if retraining
                else (
                    f"繼續閱讀 {int(float(material.get('progress') or 0))}%"
                    if float(material.get("progress") or 0) > 0
                    else "開始閱讀"
                )
            ),
            "target": "materials",
        })

    for exam in list(dashboard.get("pendingExams") or []):
        course_id = str(exam.get("courseId") or "")
        if course_id and course_id in pending_course_ids:
            continue
        remediation = bool(exam.get("remediationRequired"))
        values.append({
            "id": str(exam.get("id") or ""),
            "resourceId": str(exam.get("id") or ""),
            "courseId": course_id,
            "persona": "learner",
            "domain": "learning",
            "kind": "exam",
            "title": str(exam.get("title") or "待完成考核"),
            "status": "remediation" if remediation else "pending",
            "statusLabel": "補強再測" if remediation else "待完成考核",
            "group": str(exam.get("group") or ""),
            "area": str(exam.get("area") or "internal"),
            "dueAt": "",
            "overdue": False,
            "detail": (
                f"上次未達標 · 建議先複習 {int((exam.get('remediation') or {}).get('reviewMaterialCount') or 0)} 份教材"
                if remediation else f"及格標準 {int(exam.get('passingScore') or 80)} 分"
            ),
            "action": "exam",
            "actionLabel": "前往補強再測" if remediation else "前往考核",
            "target": "exam",
        })

    try:
        intervention_rows = list(intervention_service.mine(user).get("items") or [])
    except Exception as exc:
        LOGGER.warning(
            "command center intervention projection failed error_type=%s",
            type(exc).__name__,
        )
        intervention_rows = []

    intervention_labels = {
        "overdue": "教師逾期追蹤",
        "retraining": "教師重訓追蹤",
        "remediation": "教師補強追蹤",
    }
    case_status_labels = {
        "open": "待處理",
        "in_progress": "處理中",
        "ready_for_retest": "準備再測",
    }
    for case in intervention_rows:
        case_status = str(case.get("status") or "")
        if case_status not in intervention_service.ACTIVE_CASE_STATUSES:
            continue
        course_id = str(case.get("courseId") or "")
        kind = str(case.get("kind") or "")
        plan = dict(case.get("plan") or {})
        item = next(
            (entry for entry in values if str(entry.get("courseId") or "") == course_id),
            None,
        )
        if item is None:
            course = course_repository.get_course(course_id) or {}
            if not course:
                continue
            item = {
                "id": str(case.get("id") or course_id),
                "resourceId": course_id,
                "courseId": course_id,
                "persona": "learner",
                "domain": "learning",
                "kind": "intervention",
                "title": str(course.get("title") or case.get("courseTitle") or "教師追蹤項目"),
                "status": case_status,
                "statusLabel": intervention_labels.get(kind, "教師追蹤"),
                "group": str(course.get("group") or ""),
                "area": str(course.get("area") or "internal"),
                "dueAt": str(plan.get("dueAt") or ""),
                "overdue": kind == "overdue",
                "detail": str(case.get("learnerMessage") or "請依教師追蹤計畫完成後續學習。"),
                "action": "intervention",
                "actionLabel": "查看學習要求",
                "target": "materials",
            }
            values.append(item)

        item["interventionId"] = str(case.get("id") or "")
        item["interventionStatus"] = case_status
        item["interventionKind"] = kind
        item["interventionPlan"] = plan
        item["status"] = case_status
        item["statusLabel"] = (
            intervention_labels.get(kind, "教師追蹤")
            + " · "
            + case_status_labels.get(case_status, case_status)
        )
        if case.get("learnerMessage"):
            item["detail"] = str(case.get("learnerMessage") or "")

        review_materials = list(plan.get("reviewMaterials") or [])
        if kind == "remediation":
            quiz_id = str(plan.get("quizCategoryId") or "")
            if case_status == "ready_for_retest" and quiz_id:
                item["target"] = "exam"
                item["resourceId"] = quiz_id
                item["materialId"] = ""
                item["actionLabel"] = "進行再測"
            elif review_materials:
                material_id = str(review_materials[0].get("id") or "")
                item["target"] = "materials"
                item["materialId"] = material_id
                item["actionLabel"] = "先完成補強教材"
            elif quiz_id:
                item["target"] = "exam"
                item["resourceId"] = quiz_id
                item["actionLabel"] = "前往補強再測"
        elif kind == "retraining" and review_materials:
            material_id = str(review_materials[0].get("id") or "")
            item["target"] = "materials"
            item["materialId"] = material_id
            item["actionLabel"] = "重新閱讀指定教材"
        elif kind == "overdue":
            item["overdue"] = True
            if not item.get("actionLabel"):
                item["actionLabel"] = "優先完成逾期項目"

    return values


def _teacher_review_items(user: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not has_permission(user, "evaluation.review"):
        return []
    values = []
    try:
        rows = exam_records.list_records()
    except Exception as exc:
        LOGGER.warning("command center review projection failed error_type=%s", type(exc).__name__)
        return values
    for row in rows:
        if str(row.get("reviewStatus") or "completed") != "pending":
            continue
        if not exam_records.can_review_record(user, row):
            continue
        area = str(row.get("trainingArea") or "internal")
        group = str(row.get("groupKey") or "grpBio")
        values.append({
            "id": str(row.get("id") or ""),
            "resourceId": str(row.get("id") or ""),
            "persona": "teacher",
            "domain": "assessment",
            "kind": "review",
            "title": str(row.get("quizTitle") or "待人工批改考核"),
            "status": "pending_review",
            "statusLabel": "待批改",
            "group": group,
            "area": area,
            "dueAt": "",
            "overdue": False,
            "detail": f"{str(row.get('name') or row.get('empId') or '學員')} 的作答等待人工批改",
            "action": "review",
            "actionLabel": "前往批改",
            "target": "assessment",
        })
    return values


def _teacher_material_failure_items(user: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not has_permission(user, "material.manage"):
        return []
    values = []
    try:
        jobs = worker_repository.list_material_jobs(80)
    except Exception as exc:
        LOGGER.warning("command center material failure projection failed error_type=%s", type(exc).__name__)
        return values
    for job in jobs:
        if str(job.get("status") or "") != "failed":
            continue
        try:
            full = worker_repository.get_material_job(str(job.get("id") or ""), include_payload=True) or job
        except Exception as exc:
            LOGGER.warning(
                "command center material job detail fallback job_id=%s error_type=%s",
                str(job.get("id") or "")[:100],
                type(exc).__name__,
            )
            full = job
        payload = full.get("payload") if isinstance(full.get("payload"), Mapping) else {}
        area = str(payload.get("area") or full.get("area") or "internal")
        group = str(payload.get("group") or full.get("group") or "grpBio")
        if not _visible_to_teacher(user, {"area": area, "group": group}):
            continue
        retained = str(full.get("stagingBackend") or "") == "r2" and bool(full.get("stagingKey"))
        # "需要我處理" must stay actionable. Historical failures whose
        # source object is already gone remain visible in the canonical Job
        # history, but there is nothing a teacher can retry from this queue.
        if not retained:
            continue
        values.append({
            "id": str(full.get("id") or ""),
            "resourceId": str(full.get("id") or ""),
            "persona": "teacher",
            "domain": "materials",
            "kind": "material_failure",
            "title": str(payload.get("title") or full.get("originalName") or "教材處理失敗"),
            "status": "needs_attention",
            "statusLabel": "教材需要處理",
            "group": group,
            "area": area,
            "dueAt": "",
            "overdue": False,
            "detail": str(full.get("error") or full.get("detail") or "背景教材處理失敗"),
            "sourceRetained": retained,
            "action": "material_jobs",
            "actionLabel": "直接重新處理",
            "target": "course-materials",
        })
    return values


def _teacher_intervention_items(user: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not (
        has_permission(user, "training.compliance.read")
        and has_permission(user, "learning.assign")
    ):
        return []
    try:
        data = intervention_service.manager_list(user)
    except Exception as exc:
        LOGGER.warning(
            "command center intervention manager projection failed error_type=%s",
            type(exc).__name__,
        )
        return []

    values = []
    for item in list(data.get("items") or []):
        status = str(item.get("status") or "")
        if status not in intervention_service.ACTIVE_CASE_STATUSES:
            continue
        course_id = str(item.get("courseId") or "")
        course = course_repository.get_course(course_id) or {}
        if not course or not _visible_to_teacher(user, course):
            continue
        ready = bool(item.get("resolutionEligible"))
        kind = str(item.get("kind") or "")
        values.append({
            "id": str(item.get("id") or ""),
            "resourceId": str(item.get("id") or ""),
            "courseId": course_id,
            "persona": "teacher",
            "domain": "interventions",
            "kind": "intervention",
            "title": str(course.get("title") or "學員介入追蹤"),
            "status": "ready_to_resolve" if ready else status,
            "statusLabel": "證據已解除，可結案" if ready else {
                "remediation": "補強追蹤",
                "retraining": "重訓追蹤",
                "overdue": "逾期追蹤",
            }.get(kind, "介入追蹤"),
            "group": str(course.get("group") or ""),
            "area": str(course.get("area") or "internal"),
            "dueAt": str((item.get("plan") or {}).get("dueAt") or ""),
            "overdue": kind == "overdue",
            "detail": (
                "學員已解除原異常，請確認證據後結案。"
                if ready
                else str(item.get("learnerMessage") or "此學員已有正式介入案件待追蹤。")
            ),
            "username": str(item.get("username") or ""),
            "action": "intervention",
            "actionLabel": "前往結案" if ready else "查看介入追蹤",
            "target": "teacher",
            "interventionId": str(item.get("id") or ""),
            "resolutionEligible": ready,
        })
    return values


def _teacher_due_items(user: Mapping[str, Any], current: dt.datetime) -> list[dict[str, Any]]:
    if not has_permission(user, "learning.assign"):
        return []
    values = []
    try:
        assignments = assignment_service.admin_list(user, include_inactive=False)
    except Exception as exc:
        LOGGER.warning("command center assignment projection failed error_type=%s", type(exc).__name__)
        return values
    course_cache: dict[str, dict[str, Any]] = {}
    for assignment in assignments:
        due = _parse_datetime(assignment.get("dueAt"))
        if not due or due > current + TEACHER_DUE_WINDOW:
            continue
        course_id = str(assignment.get("courseId") or "")
        if course_id not in course_cache:
            course_cache[course_id] = course_repository.get_course(course_id) or {}
        course = course_cache[course_id]
        title = str(course.get("title") or course_id or "課程")
        values.append({
            "id": str(assignment.get("id") or ""),
            "resourceId": course_id,
            "courseId": course_id,
            "persona": "teacher",
            "domain": "assignments",
            "kind": "due",
            "title": title,
            "status": "overdue" if due < current else "due_soon",
            "statusLabel": "已逾期" if due < current else "即將到期",
            "group": str(assignment.get("group") or course.get("group") or ""),
            "area": str(assignment.get("area") or course.get("area") or ""),
            "dueAt": due.isoformat(),
            "overdue": due < current,
            "detail": "課程指派截止時間已到" if due < current else "課程指派將在 7 天內到期",
            "action": "assignment",
            "actionLabel": "查看課程指派",
            "target": "course-materials",
        })
    return values


def _teacher_draft_items(user: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not has_permission(user, "course.manage"):
        return []
    values = []
    try:
        courses = course_repository.list_courses(None, None, True)
    except Exception as exc:
        LOGGER.warning("command center draft projection failed error_type=%s", type(exc).__name__)
        return values
    for course in courses:
        if course.get("active", True):
            continue
        lifecycle = str(
            course.get("lifecycleStatus")
            or ("published" if course.get("active", True) else "draft")
        )
        if lifecycle not in {"draft", "ready"}:
            continue
        if not _visible_to_teacher(user, course):
            continue
        course_id = str(course.get("id") or "")
        values.append({
            "id": course_id,
            "resourceId": course_id,
            "courseId": course_id,
            "persona": "teacher",
            "domain": "courses",
            "kind": "draft",
            "title": str(course.get("title") or "未命名課程草稿"),
            "status": lifecycle,
            "statusLabel": "可發布" if lifecycle == "ready" else "未發布草稿",
            "group": str(course.get("group") or ""),
            "area": str(course.get("area") or ""),
            "dueAt": "",
            "overdue": False,
            "detail": (
                "課程已通過發布檢查，等待正式發布。"
                if lifecycle == "ready"
                else "此課程仍是草稿，學員尚無法使用。"
            ),
            "action": "draft",
            "actionLabel": "正式發布" if lifecycle == "ready" else "繼續編輯",
            "target": "course-materials",
        })
    return values


def _teacher_action_items(user: Mapping[str, Any], current: dt.datetime) -> list[dict[str, Any]]:
    if not any(has_permission(user, permission) for permission in (
        "course.manage", "material.manage", "evaluation.review", "learning.assign"
    )):
        return []
    values = []
    values.extend(_teacher_review_items(user))
    values.extend(_teacher_material_failure_items(user))
    values.extend(_teacher_intervention_items(user))
    values.extend(_teacher_due_items(user, current))
    values.extend(_teacher_draft_items(user))
    return values


def build_summary(
    user: Optional[Mapping[str, Any]],
    *,
    now: Optional[dt.datetime] = None,
) -> dict[str, Any]:
    """Return one authenticated user's read-only command-center projection."""
    if not user:
        raise ApiError(
            "LOGIN_REQUIRED",
            "請先登入後再查看待辦。",
            status=401,
            extra={"loginRequired": True},
        )

    profile = audience.current_profile(user)
    role = normalize_role(user.get("role", "student"))
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    current = current.astimezone(dt.timezone.utc)

    learner_items = _learner_action_items(user, current) if _has_learner_persona(user, role) else []

    actionable = ACTIONABLE_PGY.get(role, {}) if profile["pgyLearner"] else {}
    assignments = pgy_service.list_assignments(user) if actionable else []
    pgy_items: list[dict[str, Any]] = []

    for assignment in assignments:
        status = str(assignment.get("status") or "")
        action_spec = actionable.get(status)
        if not action_spec:
            continue
        action, action_label = action_spec
        due_at = str(assignment.get("dueAt") or "")
        pgy_items.append(
            {
                "id": str(assignment.get("id") or ""),
                "resourceId": str(assignment.get("id") or ""),
                "persona": "learner" if role == "student" else "teacher",
                "domain": "pgy",
                "kind": "assignment",
                "title": str(assignment.get("title") or "PGY 訓練指派"),
                "status": status,
                "statusLabel": STATUS_LABELS.get(status, status),
                "group": str(assignment.get("group") or ""),
                "area": "pgy",
                "dueAt": due_at,
                "overdue": _is_overdue(due_at, current),
                "action": action,
                "actionLabel": action_label,
                "target": "pgy-workflow",
            }
        )

    teacher_items = _teacher_action_items(user, current)
    items = [*learner_items, *pgy_items, *teacher_items]
    items.sort(key=_task_sort_key)
    overdue = sum(1 for item in items if item.get("overdue"))
    learner_count = sum(1 for item in items if item.get("persona") == "learner")
    teacher_counts = {
        "review": sum(1 for item in teacher_items if item.get("kind") == "review"),
        "materialFailure": sum(1 for item in teacher_items if item.get("kind") == "material_failure"),
        "intervention": sum(1 for item in teacher_items if item.get("kind") == "intervention"),
        "due": sum(1 for item in teacher_items if item.get("kind") == "due"),
        "draft": sum(1 for item in teacher_items if item.get("kind") == "draft"),
    }
    return {
        "role": role,
        "audience": profile["audience"],
        "pgyLearner": profile["pgyLearner"],
        "scope": ["online", "pgy"] if profile["pgyLearner"] else ["online"],
        "generatedAt": current.isoformat(),
        "counts": {
            "total": len(items),
            "overdue": overdue,
            "pgy": len(pgy_items),
            "learner": learner_count,
            "teacher": len(teacher_items),
            **teacher_counts,
        },
        "nextAction": next(
            (dict(item) for item in items if item.get("persona") == "learner"),
            None,
        ),
        "nextTeacherAction": next(
            (dict(item) for item in items if item.get("persona") == "teacher"),
            None,
        ),
        "items": items,
    }