"""Canonical learner progress projection for product-converged surfaces.

Online learning completion continues to come from dashboard_summary(), which owns
material/exam/course completion semantics. PGY assignment completion comes from
the formal competency matrix and is kept as a separate metric rather than being
blended into an invented composite score.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

from teacher_app.command_center import audience, competency, dashboard_service
from teacher_app.common.errors import ApiError


def build_progress(user: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    if not user:
        raise ApiError("LOGIN_REQUIRED", "請先登入後再查看學習進度。", status=401, extra={"loginRequired": True})

    profile = audience.current_profile(user)
    dashboard = dashboard_service.dashboard_summary(user)
    result = {
        "audience": profile["audience"],
        "pgyLearner": bool(profile["pgyLearner"]),
        "online": {
            "percent": int(dashboard.get("progressPercent") or 0),
            "materialsCompleted": int(dashboard.get("materialsCompleted") or 0),
            "materialsTotal": int(dashboard.get("materialsTotal") or 0),
            "examsPassed": int(dashboard.get("examsPassed") or 0),
            "examsTotal": int(dashboard.get("examsTotal") or 0),
            "examsPending": int(dashboard.get("examsPending") or 0),
            "activeCourses": int(dashboard.get("activeCourses") or 0),
            "scopeSource": str(dashboard.get("scopeSource") or "profile"),
        },
        "pgy": None,
        "interpretation": "separate_online_and_pgy_progress_sources",
    }

    if profile["pgyLearner"]:
        matrix = competency.build_competency_matrix(user)
        summary = matrix.get("summary") or {}
        result["pgy"] = {
            "percent": float(summary.get("assignmentCompletionPercent") or 0),
            "assignmentsCompleted": int(summary.get("assignmentsCompleted") or 0),
            "assignmentsTotal": int(summary.get("assignments") or 0),
            "assignmentsOverdue": int(summary.get("assignmentsOverdue") or 0),
            "averageAssessmentScore": summary.get("averageAssessmentScore"),
        }
    return result


__all__ = ["build_progress"]
