"""Canonical Question Bank item analytics aggregation."""
from __future__ import annotations

from collections import Counter

from teacher_app.assessments import repository


MIN_SUFFICIENT_ATTEMPTS = 10


def get_question_analytics(question_id: str) -> dict:
    rows = repository.list_question_attempt_analytics(question_id)
    attempt_count = len(rows)
    if attempt_count < MIN_SUFFICIENT_ATTEMPTS:
        return {
            "attemptCount": attempt_count,
            "sufficientData": False,
            "message": "資料不足",
        }

    counts = dict(Counter(row.get("selected_option") for row in rows))
    correct = str(repository.get_bank_question_correct(question_id) or "")
    return {
        "attemptCount": attempt_count,
        "sufficientData": True,
        "correctRate": round(
            sum(bool(row.get("is_correct")) for row in rows) / attempt_count,
            3,
        ),
        "optionSelectionCounts": counts,
        "distractorDistribution": {
            key: value
            for key, value in counts.items()
            if str(key) != correct
        },
    }
