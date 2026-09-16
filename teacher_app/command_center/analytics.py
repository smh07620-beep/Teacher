"""Teacher 7.1 M3 read-only learning analytics projection.

Analytics are derived from existing learning progress, exam records, PGY
assignments, and PGY assessments. No synthetic mastery score is created.
"""
from __future__ import annotations

import datetime as dt
from statistics import mean
from typing import Any, Mapping, Optional, Sequence

from teacher_app.command_center.competency import ASSESSMENT_KEYS, load_assignment_rows, load_assessment_rows
from teacher_app.command_center.scope import visible_learners
from teacher_app.common.db import get_connection, placeholder


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


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off"}
    return bool(value)


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _in_clause(kind: str, values: Sequence[str]) -> str:
    ph = placeholder(kind)
    return ",".join(ph for _ in values)


def load_learning_rows(usernames: Sequence[str]) -> list[dict[str, Any]]:
    values = [str(value).strip().lower() for value in usernames if str(value).strip()]
    if not values:
        return []
    conn, kind = get_connection()
    try:
        marks = _in_clause(kind, values)
        rows = conn.execute(
            f"""
            SELECT material_id,username,progress,completed,last_viewed_at,completed_at
            FROM learning_progress
            WHERE username IN ({marks})
            """,
            tuple(values),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def load_legacy_material_rows(emp_ids: Sequence[str]) -> list[dict[str, Any]]:
    values = [str(value).strip() for value in emp_ids if str(value).strip()]
    if not values:
        return []
    conn, kind = get_connection()
    try:
        marks = _in_clause(kind, values)
        rows = conn.execute(
            f"""
            SELECT emp_id,material_id,completed_at
            FROM material_progress
            WHERE emp_id IN ({marks})
            """,
            tuple(values),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def load_exam_rows(emp_ids: Sequence[str]) -> list[dict[str, Any]]:
    values = [str(value).strip() for value in emp_ids if str(value).strip()]
    if not values:
        return []
    conn, kind = get_connection()
    try:
        marks = _in_clause(kind, values)
        rows = conn.execute(
            f"""
            SELECT id,emp_id,quiz_title,score,status,review_status,passing_score,
                   group_key,training_area,created_at
            FROM exam_records
            WHERE emp_id IN ({marks})
            ORDER BY created_at DESC
            """,
            tuple(values),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _latest(values: Sequence[Any]) -> str:
    parsed = [(_parse_datetime(value), str(value or "")) for value in values]
    valid = [item for item in parsed if item[0] is not None]
    return max(valid, key=lambda item: item[0])[1] if valid else ""


def _material_metrics(
    learner: Mapping[str, Any],
    smart_rows: Sequence[Mapping[str, Any]],
    legacy_rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    username = str(learner.get("username") or "").strip().lower()
    emp_id = str(learner.get("empId") or "").strip()
    records: dict[str, dict[str, Any]] = {}

    for row in smart_rows:
        if str(row.get("username") or "").strip().lower() != username:
            continue
        material_id = str(row.get("material_id") or "").strip()
        if not material_id:
            continue
        progress = max(0.0, min(100.0, _float(row.get("progress"))))
        records[material_id] = {
            "progress": progress,
            "completed": _truthy(row.get("completed")),
            "last": str(row.get("last_viewed_at") or row.get("completed_at") or ""),
        }

    for row in legacy_rows:
        if str(row.get("emp_id") or "").strip() != emp_id:
            continue
        material_id = str(row.get("material_id") or "").strip()
        if not material_id:
            continue
        item = records.setdefault(material_id, {"progress": 100.0, "completed": True, "last": ""})
        item["completed"] = True
        if item["progress"] <= 0:
            item["progress"] = 100.0
        completed_at = str(row.get("completed_at") or "")
        item["last"] = _latest([item.get("last"), completed_at])

    values = list(records.values())
    tracked = len(values)
    completed = sum(1 for item in values if item["completed"])
    progress_values = [float(item["progress"]) for item in values]
    last = _latest([item.get("last") for item in values])
    events = [(str(item.get("last") or ""), "materials") for item in values if item.get("last")]
    return {
        "tracked": tracked,
        "completed": completed,
        "completionRate": round((completed / tracked) * 100, 1) if tracked else 0.0,
        "averageProgress": round(mean(progress_values), 1) if progress_values else None,
        "lastViewedAt": last,
    }, events


def _exam_metrics(emp_id: str, rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    items = [row for row in rows if str(row.get("emp_id") or "").strip() == emp_id]
    reviewed = [row for row in items if str(row.get("review_status") or "completed") != "pending"]
    scores = [_float(row.get("score")) for row in reviewed]
    passed = sum(1 for row in reviewed if _float(row.get("score")) >= _float(row.get("passing_score") or 80))
    pending = len(items) - len(reviewed)
    latest_row = max(
        items,
        key=lambda row: _parse_datetime(row.get("created_at")) or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
        default=None,
    )
    events = [(str(row.get("created_at") or ""), "exams") for row in items if row.get("created_at")]
    return {
        "attempts": len(items),
        "reviewedAttempts": len(reviewed),
        "pendingReview": pending,
        "averageScore": round(mean(scores), 1) if scores else None,
        "passed": passed,
        "passRate": round((passed / len(reviewed)) * 100, 1) if reviewed else 0.0,
        "latestScore": round(_float(latest_row.get("score")), 1) if latest_row else None,
        "lastAttemptAt": str(latest_row.get("created_at") or "") if latest_row else "",
    }, events


def _pgy_metrics(
    learner: Mapping[str, Any],
    assignments: Sequence[Mapping[str, Any]],
    assessments: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    username = str(learner.get("username") or "").strip().lower()
    emp_id = str(learner.get("empId") or "").strip()
    learner_assignments = [
        row for row in assignments
        if str(row.get("learner_username") or "").strip().lower() == username
        and str(row.get("status") or "") != "cancelled"
    ]
    completed = [row for row in learner_assignments if str(row.get("status") or "") == "finalized"]
    learner_assessments = [
        row for row in assessments
        if str(row.get("emp_id") or "").strip() == emp_id
        and str(row.get("assessment_type") or "") in ASSESSMENT_KEYS
        and str(row.get("status") or "completed") == "completed"
    ]
    scores = [_float(row.get("overall_score")) for row in learner_assessments]
    events = []
    for row in completed:
        if row.get("updated_at"):
            events.append((str(row.get("updated_at")), "pgy"))
    for row in learner_assessments:
        timestamp = str(row.get("created_at") or row.get("assessment_date") or "")
        if timestamp:
            events.append((timestamp, "assessments"))
    total = len(learner_assignments)
    return {
        "assignments": total,
        "completedAssignments": len(completed),
        "completionRate": round((len(completed) / total) * 100, 1) if total else 0.0,
        "assessments": len(learner_assessments),
        "assessmentAverage": round(mean(scores), 2) if scores else None,
    }, events


def _month_keys(now: dt.datetime, count: int = 6) -> list[str]:
    year = now.year
    month = now.month
    values = []
    for offset in range(count - 1, -1, -1):
        y = year
        m = month - offset
        while m <= 0:
            y -= 1
            m += 12
        values.append(f"{y:04d}-{m:02d}")
    return values


def project_analytics(
    scope: Mapping[str, Any],
    learners: Sequence[Mapping[str, Any]],
    learning_rows: Sequence[Mapping[str, Any]],
    legacy_material_rows: Sequence[Mapping[str, Any]],
    exam_rows: Sequence[Mapping[str, Any]],
    assignments: Sequence[Mapping[str, Any]],
    assessments: Sequence[Mapping[str, Any]],
    *,
    now: Optional[dt.datetime] = None,
) -> dict[str, Any]:
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    current = current.astimezone(dt.timezone.utc)

    output = []
    all_material_progress: list[float] = []
    material_tracked = material_completed = 0
    all_exam_scores: list[float] = []
    exam_reviewed = exam_passed = exam_attempts = exam_pending = 0
    pgy_assignments = pgy_completed = 0
    all_assessment_scores: list[float] = []
    activity: list[tuple[str, str]] = []
    exam_areas: dict[str, int] = {}

    for learner in learners:
        materials, material_events = _material_metrics(learner, learning_rows, legacy_material_rows)
        exams, exam_events = _exam_metrics(str(learner.get("empId") or ""), exam_rows)
        pgy, pgy_events = _pgy_metrics(learner, assignments, assessments)
        activity.extend(material_events + exam_events + pgy_events)

        smart_for_learner = [
            row for row in learning_rows
            if str(row.get("username") or "").strip().lower() == str(learner.get("username") or "").strip().lower()
        ]
        legacy_ids = {
            str(row.get("material_id") or "") for row in legacy_material_rows
            if str(row.get("emp_id") or "").strip() == str(learner.get("empId") or "").strip()
        }
        smart_ids = {str(row.get("material_id") or "") for row in smart_for_learner}
        all_material_progress.extend([max(0.0, min(100.0, _float(row.get("progress")))) for row in smart_for_learner])
        all_material_progress.extend([100.0 for _material_id in (legacy_ids - smart_ids)])
        material_tracked += materials["tracked"]
        material_completed += materials["completed"]

        learner_exam_rows = [row for row in exam_rows if str(row.get("emp_id") or "").strip() == str(learner.get("empId") or "").strip()]
        reviewed = [row for row in learner_exam_rows if str(row.get("review_status") or "completed") != "pending"]
        all_exam_scores.extend([_float(row.get("score")) for row in reviewed])
        exam_attempts += len(learner_exam_rows)
        exam_reviewed += len(reviewed)
        exam_pending += len(learner_exam_rows) - len(reviewed)
        exam_passed += sum(1 for row in reviewed if _float(row.get("score")) >= _float(row.get("passing_score") or 80))
        for row in learner_exam_rows:
            area = str(row.get("training_area") or "unknown")
            exam_areas[area] = exam_areas.get(area, 0) + 1

        learner_assignment_rows = [
            row for row in assignments
            if str(row.get("learner_username") or "").strip().lower() == str(learner.get("username") or "").strip().lower()
            and str(row.get("status") or "") != "cancelled"
        ]
        pgy_assignments += len(learner_assignment_rows)
        pgy_completed += sum(1 for row in learner_assignment_rows if str(row.get("status") or "") == "finalized")
        learner_assessment_rows = [
            row for row in assessments
            if str(row.get("emp_id") or "").strip() == str(learner.get("empId") or "").strip()
            and str(row.get("assessment_type") or "") in ASSESSMENT_KEYS
            and str(row.get("status") or "completed") == "completed"
        ]
        all_assessment_scores.extend([_float(row.get("overall_score")) for row in learner_assessment_rows])

        output.append({
            "username": str(learner.get("username") or ""),
            "name": str(learner.get("name") or ""),
            "empId": str(learner.get("empId") or ""),
            "group": str(learner.get("group") or ""),
            "materials": materials,
            "exams": exams,
            "pgy": pgy,
        })

    months = {key: {"month": key, "materials": 0, "exams": 0, "pgy": 0, "assessments": 0} for key in _month_keys(current)}
    for timestamp, domain in activity:
        parsed = _parse_datetime(timestamp)
        if not parsed:
            continue
        key = parsed.strftime("%Y-%m")
        if key in months and domain in months[key]:
            months[key][domain] += 1

    output.sort(key=lambda item: (item["group"], item["name"], item["empId"]))
    return {
        "scope": dict(scope),
        "generatedAt": current.isoformat(),
        "summary": {
            "learners": len(output),
            "materialsTracked": material_tracked,
            "materialsCompleted": material_completed,
            "materialCompletionRate": round((material_completed / material_tracked) * 100, 1) if material_tracked else 0.0,
            "averageMaterialProgress": round(mean(all_material_progress), 1) if all_material_progress else None,
            "examAttempts": exam_attempts,
            "examReviewedAttempts": exam_reviewed,
            "examPendingReview": exam_pending,
            "averageExamScore": round(mean(all_exam_scores), 1) if all_exam_scores else None,
            "examPassRate": round((exam_passed / exam_reviewed) * 100, 1) if exam_reviewed else 0.0,
            "pgyAssignments": pgy_assignments,
            "pgyCompletedAssignments": pgy_completed,
            "pgyCompletionRate": round((pgy_completed / pgy_assignments) * 100, 1) if pgy_assignments else 0.0,
            "averagePgyAssessmentScore": round(mean(all_assessment_scores), 2) if all_assessment_scores else None,
        },
        "examAreas": exam_areas,
        "timeline": list(months.values()),
        "learners": output,
        "interpretation": "descriptive_existing_records_only",
    }


def build_learning_analytics(user: Optional[Mapping[str, Any]], *, now: Optional[dt.datetime] = None) -> dict[str, Any]:
    scope, learners = visible_learners(user)
    usernames = [item["username"] for item in learners]
    emp_ids = [item["empId"] for item in learners]
    learning_rows = load_learning_rows(usernames)
    legacy_material_rows = load_legacy_material_rows(emp_ids)
    exam_rows = load_exam_rows(emp_ids)
    assignments = load_assignment_rows(usernames)
    assessments = load_assessment_rows(emp_ids)
    return project_analytics(
        scope,
        learners,
        learning_rows,
        legacy_material_rows,
        exam_rows,
        assignments,
        assessments,
        now=now,
    )