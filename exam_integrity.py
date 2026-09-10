"""Compatibility adapter for the modular Teacher 6.5 exam implementation.

The Render entrypoint still imports ``register_exam_integrity`` from here. Exam
grading, persistence, orchestration and route definitions now live under
``teacher_app.exams``.
"""

from teacher_app.exams.grading import (
    normalize_indices as _normalize_indices,
    sanitize_answer_config as _sanitize_answer_config,
    sanitize_question,
    score_question,
)
from teacher_app.exams.routes import register_legacy_exam_routes


def register_exam_integrity(base):
    return register_legacy_exam_routes(base)


__all__ = [
    "_normalize_indices",
    "_sanitize_answer_config",
    "sanitize_question",
    "score_question",
    "register_exam_integrity",
]
