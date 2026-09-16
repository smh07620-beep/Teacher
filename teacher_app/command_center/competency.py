"""Teacher 7.1 M2 PGY competency/progress matrix projection.

The matrix reports existing formal assessment tools and PGY assignment progress.
It does not invent a new proficiency score or mutate clinical workflow state.
"""
from __future__ import annotations

import datetime as dt
from statistics import mean
from typing import Any, Mapping, Optional, Sequence

from teacher_app.command_center.scope import visible_learners
from teacher_app.common.db import get_connection, placeholder


ASSESSMENT_TYPES = (
    ("dops", "DOPS"),
    ("mini_cex", "MINI-CEX"),
    ("cbd", "CBD"),
    ("checklist", "CHECKLIST"),
    ("qc", "QC"),
    ("feedback360", "360"),
    ("report", "REPORT"),
    ("qi", "QI"),
    ("reflection", "REFLECTION"),
    ("attendance", "ATTENDANCE"),
)
ASSESSMENT_KEYS = {key for key, _label in ASSESSMENT_TYPES}


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


def _in_clause(kind: str, values: Sequence[str]) -> str:
    ph = placeholder(kind)
    return ",".join(ph for _ in values)


def load_assignment_rows(usernames: Sequence[str]) -> list[dict[str, Any]]:
    values = [str(value).strip().lower() for value in usernames if str(value).strip()]
    if not values:
        return []
    conn, kind = get_connection()
    try:
        marks = _in_clause(kind, values)
        rows = conn.execute(
            f"""
            SELECT id,learner_username,group_key,title,due_at,status,updated_at
            FROM pgy_assignments
            WHERE training_area='pgy'
              AND learner_username IN ({marks})
            """,
            tuple(values),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def load_assessment_rows(emp_ids: Sequence[str]) -> list[dict[str, Any]]:
    values = [str(value).strip() for value in emp_ids if str(value).strip()]
    if not values:
        return []
    conn, kind = get_connection()
    try:
        marks = _in_clause(kind, values)
        rows = conn.execute(
            f"""
            SELECT id,assessment_type,group_key,name,emp_id,assessment_date,
                   title,overall_score,status,created_at
            FROM pgy_assessments
            WHERE emp_id IN ({marks})
            ORDER BY created_at DESC
            """,
            tuple(values),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _score(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _cell(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"count": 0, "averageScore": None, "latestScore": None, "latestDate": ""}
    scores = [_score(row.get("overall_score")) for row in rows]
    latest = max(
        rows,
        key=lambda row: _parse_datetime(row.get("assessment_date") or row.get("created_at"))
        or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
    )
    return {
        "count": len(rows),
        "averageScore": round(mean(scores), 2),
        "latestScore": round(_score(latest.get("overall_score")), 2),
        "latestDate": str(latest.get("assessment_date") or latest.get("created_at") or ""),
    }


def project_matrix(
    scope: Mapping[str, Any],
    learners: Sequence[Mapping[str, Any]],
    assignments: Sequence[Mapping[str, Any]],
    assessments: Sequence[Mapping[str, Any]],
    *,
    now: Optional[dt.datetime] = None,
) -> dict[str, Any]:
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    current = current.astimezone(dt.timezone.utc)

    assignment_by_user: dict[str, list[Mapping[str, Any]]] = {}
    for row in assignments:
        assignment_by_user.setdefault(str(row.get("learner_username") or "").strip().lower(), []).append(row)

    assessment_by_emp: dict[str, list[Mapping[str, Any]]] = {}
    for row in assessments:
        if str(row.get("assessment_type") or "") not in ASSESSMENT_KEYS:
            continue
        if str(row.get("status") or "completed") != "completed":
            continue
        assessment_by_emp.setdefault(str(row.get("emp_id") or "").strip(), []).append(row)

    output = []
    all_scores: list[float] = []
    total_assignments = completed_assignments = overdue_assignments = 0

    for learner in learners:
        username = str(learner.get("username") or "").strip().lower()
        emp_id = str(learner.get("empId") or "").strip()
        learner_assignments = [
            row for row in assignment_by_user.get(username, [])
            if str(row.get("status") or "") != "cancelled"
        ]
        completed = sum(1 for row in learner_assignments if str(row.get("status") or "") == "finalized")
        overdue = 0
        for row in learner_assignments:
            if str(row.get("status") or "") == "finalized":
                continue
            due = _parse_datetime(row.get("due_at"))
            if due and due < current:
                overdue += 1

        learner_assessments = assessment_by_emp.get(emp_id, [])
        competencies = {}
        for key, _label in ASSESSMENT_TYPES:
            rows = [row for row in learner_assessments if str(row.get("assessment_type") or "") == key]
            competencies[key] = _cell(rows)

        scores = [_score(row.get("overall_score")) for row in learner_assessments]
        all_scores.extend(scores)
        total = len(learner_assignments)
        progress_percent = round((completed / total) * 100, 1) if total else 0.0
        coverage_types = sum(1 for item in competencies.values() if item["count"])

        total_assignments += total
        completed_assignments += completed
        overdue_assignments += overdue
        output.append({
            "username": username,
            "name": str(learner.get("name") or ""),
            "empId": emp_id,
            "group": str(learner.get("group") or ""),
            "progress": {
                "assignmentsTotal": total,
                "assignmentsCompleted": completed,
                "assignmentsOverdue": overdue,
                "percent": progress_percent,
            },
            "assessmentSummary": {
                "count": len(learner_assessments),
                "averageScore": round(mean(scores), 2) if scores else None,
                "coverageTypes": coverage_types,
                "coverageTotal": len(ASSESSMENT_TYPES),
            },
            "competencies": competencies,
        })

    output.sort(key=lambda item: (item["group"], item["name"], item["empId"]))
    return {
        "scope": dict(scope),
        "generatedAt": current.isoformat(),
        "assessmentTypes": [{"key": key, "label": label} for key, label in ASSESSMENT_TYPES],
        "summary": {
            "learners": len(output),
            "assignments": total_assignments,
            "assignmentsCompleted": completed_assignments,
            "assignmentsOverdue": overdue_assignments,
            "assignmentCompletionPercent": round((completed_assignments / total_assignments) * 100, 1)
            if total_assignments else 0.0,
            "assessments": sum(item["assessmentSummary"]["count"] for item in output),
            "averageAssessmentScore": round(mean(all_scores), 2) if all_scores else None,
        },
        "learners": output,
        "interpretation": "matrix_by_formal_assessment_tool",
    }


def build_competency_matrix(user: Optional[Mapping[str, Any]], *, now: Optional[dt.datetime] = None) -> dict[str, Any]:
    scope, learners = visible_learners(user)
    assignments = load_assignment_rows([item["username"] for item in learners])
    assessments = load_assessment_rows([item["empId"] for item in learners])
    return project_matrix(scope, learners, assignments, assessments, now=now)
