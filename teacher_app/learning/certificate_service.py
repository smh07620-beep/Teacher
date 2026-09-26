"""Issue and project immutable course-completion evidence for learners."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from typing import Any, Mapping

from teacher_app.assessments import repository as assessment_repository
from teacher_app.common.errors import ApiError
from teacher_app.courses import repository as course_repository
from teacher_app.learning import access as learning_access
from teacher_app.learning import assignment_service
from teacher_app.learning import certificate_repository
from teacher_app.learning import progress_service
from teacher_app.learning import versioning
from teacher_app.materials import repository as material_repository


def _fail(code: str, message: str, status: int) -> ApiError:
    return ApiError(code, message, status=status)


def _identity(user: Mapping[str, Any] | None) -> tuple[str, str, str]:
    username = str((user or {}).get("username") or "").strip().lower()
    emp_id = str((user or {}).get("empId") or (user or {}).get("emp_id") or "").strip()
    name = str((user or {}).get("name") or (user or {}).get("displayName") or username).strip()
    if not username or not emp_id:
        raise _fail("AUTH_REQUIRED", "請先登入。", 401)
    return username, emp_id, name


def _requirement_fingerprint(requirements: Mapping[str, Any]) -> str:
    payload = json.dumps(requirements, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _evaluate_course(
    user: Mapping[str, Any] | None,
    course_id: str,
    *,
    enforce_assignment: bool,
) -> dict[str, Any]:
    username, emp_id, name = _identity(user)
    normalized_id = str(course_id or "").strip()
    course = course_repository.get_course(normalized_id)
    if not course or not course.get("active", True):
        raise _fail("COURSE_NOT_FOUND", "找不到可用課程。", 404)
    if not learning_access.can_access_learning_item(user, course):
        raise _fail("COURSE_SCOPE_DENIED", "此課程不在你的授權範圍。", 403)

    assignments = assignment_service.list_for_user(user or {})
    assigned_ids = {
        str(item.get("courseId") or "").strip()
        for item in assignments
        if str(item.get("courseId") or "").strip()
    }
    if enforce_assignment and assignments and normalized_id not in assigned_ids:
        raise _fail("COURSE_NOT_ASSIGNED", "此課程目前未指派給你。", 403)

    area = str(course.get("area") or "internal")
    group = str(course.get("group") or "grpBio")
    progress = progress_service.my_progress(user or {}, area=area, group=group)
    completion = next(
        (item for item in progress.get("courses", []) if str(item.get("id") or "") == normalized_id),
        None,
    )
    if completion is None:
        raise _fail("COURSE_NOT_FOUND", "找不到此課程的完成狀態。", 404)

    materials = [
        item
        for item in material_repository.list_uploaded_materials(include_inactive=False)
        if str(item.get("courseId") or "") == normalized_id
        and item.get("active", True)
    ]
    categories = [
        item
        for item in assessment_repository.list_categories(group, area, False)
        if str(item.get("courseId") or "") == normalized_id
        and item.get("active", True)
    ]
    material_by_id = {str(item.get("id") or ""): item for item in materials if item.get("id")}
    category_by_id = {str(item.get("id") or ""): item for item in categories if item.get("id")}

    required_material_ids = [str(item) for item in completion.get("requiredMaterialIds", [])]
    required_exam_ids = [str(item) for item in completion.get("requiredExamIds", [])]
    requirements = {
        "courseId": normalized_id,
        "materials": [
            {
                "id": material_id,
                "requiredCompletionVersion": versioning.required_completion_version(material_by_id.get(material_id)),
            }
            for material_id in sorted(required_material_ids)
        ],
        "requiredExamIds": sorted(required_exam_ids),
        "examMode": str(completion.get("examMode") or "any"),
    }
    fingerprint = _requirement_fingerprint(requirements)

    material_rows = {
        str(row.get("material_id") or ""): row
        for row in certificate_repository.list_material_completion_rows(emp_id)
        if str(row.get("material_id") or "")
    }
    material_evidence = []
    for material_id in sorted(required_material_ids):
        material = material_by_id.get(material_id, {})
        row = material_rows.get(material_id, {})
        material_evidence.append(
            {
                "materialId": material_id,
                "title": str(material.get("title") or material.get("filename") or "教材"),
                "completedAt": str(row.get("completed_at") or ""),
                "completedVersion": max(1, int(row.get("completed_version") or 1)),
                "requiredCompletionVersion": versioning.required_completion_version(material),
                "currentVersion": versioning.current_version(material),
            }
        )

    exam_evidence = []
    seen_exams: set[str] = set()
    for record in progress.get("records", []):
        exam_id = str(record.get("quizCategoryId") or "")
        if exam_id not in required_exam_ids or exam_id in seen_exams:
            continue
        if record.get("reviewStatus") != "completed":
            continue
        try:
            passed = float(record.get("score", 0) or 0) >= float(record.get("passingScore", 80) or 80)
        except (TypeError, ValueError):
            passed = False
        if not passed:
            continue
        seen_exams.add(exam_id)
        exam_evidence.append(
            {
                "quizCategoryId": exam_id,
                "title": str(category_by_id.get(exam_id, {}).get("title") or record.get("quizTitle") or "考核"),
                "recordId": str(record.get("id") or ""),
                "score": record.get("score", 0),
                "passingScore": record.get("passingScore", 80),
                "completedAt": str(record.get("timestamp") or ""),
            }
        )

    return {
        "username": username,
        "empId": emp_id,
        "learnerName": name,
        "course": course,
        "completion": completion,
        "requirements": requirements,
        "fingerprint": fingerprint,
        "materialEvidence": material_evidence,
        "examEvidence": exam_evidence,
    }


def _status_for_certificate(user: Mapping[str, Any] | None, certificate: dict[str, Any]) -> dict[str, Any]:
    result = dict(certificate)
    try:
        current = _evaluate_course(user, str(certificate.get("courseId") or ""), enforce_assignment=False)
    except ApiError:
        result.update({"currentStatus": "historical", "currentValid": False, "requiresRetraining": False})
        return result
    current_complete = bool(current["completion"].get("completed"))
    same_requirements = current["fingerprint"] == str(certificate.get("completionFingerprint") or "")
    current_valid = bool(current_complete and same_requirements)
    result.update(
        {
            "currentStatus": "current" if current_valid else "retraining_required",
            "currentValid": current_valid,
            "requiresRetraining": not current_valid,
        }
    )
    return result


def issue_certificate(user: Mapping[str, Any] | None, course_id: str) -> dict[str, Any]:
    context = _evaluate_course(user, course_id, enforce_assignment=True)
    if not context["completion"].get("completed"):
        raise _fail("COURSE_NOT_COMPLETE", "課程尚未符合完訓條件，無法發給完訓證明。", 409)

    existing = certificate_repository.find_for_fingerprint(
        context["username"], str(context["course"].get("id") or ""), context["fingerprint"]
    )
    if existing:
        return {"issued": False, "certificate": _status_for_certificate(user, existing)}

    issued_at = dt.datetime.now(dt.timezone.utc).isoformat()
    snapshot = {
        "course": {
            "id": str(context["course"].get("id") or ""),
            "title": str(context["course"].get("title") or ""),
            "area": str(context["course"].get("area") or ""),
            "group": str(context["course"].get("group") or ""),
        },
        "learner": {
            "username": context["username"],
            "empId": context["empId"],
            "name": context["learnerName"],
        },
        "requirements": context["requirements"],
        "completion": {
            key: context["completion"].get(key)
            for key in (
                "materialsTotal", "materialsCompleted", "materialsComplete", "examRequired",
                "examPassed", "requiredMaterialIds", "requiredExamIds", "examMode",
            )
        },
        "materials": context["materialEvidence"],
        "exams": context["examEvidence"],
        "issuedAt": issued_at,
    }
    certificate_id = "CERT-" + uuid.uuid4().hex[:20].upper()
    values = {
        "id": certificate_id,
        "username": context["username"],
        "emp_id": context["empId"],
        "learner_name": context["learnerName"],
        "course_id": str(context["course"].get("id") or ""),
        "course_title": str(context["course"].get("title") or ""),
        "training_area": str(context["course"].get("area") or ""),
        "group_key": str(context["course"].get("group") or ""),
        "completion_fingerprint": context["fingerprint"],
        "evidence_json": json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")),
        "issued_at": issued_at,
    }
    try:
        certificate = certificate_repository.insert_certificate(values)
    except Exception:
        certificate = certificate_repository.find_for_fingerprint(
            context["username"], str(context["course"].get("id") or ""), context["fingerprint"]
        )
        if not certificate:
            raise
        return {"issued": False, "certificate": _status_for_certificate(user, certificate)}
    return {"issued": True, "certificate": _status_for_certificate(user, certificate)}


def list_certificates(user: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    username, _emp_id, _name = _identity(user)
    cache: dict[str, dict[str, Any]] = {}
    output = []
    for certificate in certificate_repository.list_for_user(username):
        course_id = str(certificate.get("courseId") or "")
        if course_id not in cache:
            cache[course_id] = _status_for_certificate(user, certificate)
            output.append(cache[course_id])
            continue
        current = dict(certificate)
        reference = cache[course_id]
        current["currentStatus"] = (
            "current"
            if reference.get("currentValid")
            and reference.get("completionFingerprint") == current.get("completionFingerprint")
            else "historical"
        )
        current["currentValid"] = current["currentStatus"] == "current"
        current["requiresRetraining"] = reference.get("requiresRetraining", False)
        output.append(current)
    return output


def get_certificate(user: Mapping[str, Any] | None, certificate_id: str) -> dict[str, Any]:
    username, _emp_id, _name = _identity(user)
    certificate = certificate_repository.get_certificate(certificate_id)
    if not certificate or str(certificate.get("username") or "").lower() != username:
        raise _fail("CERTIFICATE_NOT_FOUND", "找不到此完訓證明。", 404)
    return _status_for_certificate(user, certificate)


__all__ = ["get_certificate", "issue_certificate", "list_certificates"]
