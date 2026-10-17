"""Learner 錯題本: questions whose most recent graded answer was wrong (2026-10-17).

Read on demand only (one indexed query on the learner's own submitted attempts),
so it adds no background database traffic.  Correct answers and teacher
explanations stay private, exactly like the post-exam review; the learner gets
the question, what they chose, and where in the material to re-read.
"""
from __future__ import annotations

from typing import Any, Mapping

from teacher_app.exams import grading
from teacher_app.exams import repository as repo

MAX_ATTEMPTS = 40
MAX_ITEMS = 200


def _username(user: Mapping[str, Any]) -> str:
    return str(user.get("username") or "").strip().lower()[:100]


def build(user: Mapping[str, Any], base=None) -> dict[str, Any]:
    username = _username(user)
    if not username:
        return {"items": [], "count": 0}
    conn, kind = repo._connect(base)
    try:
        ph = repo.placeholder(kind)
        attempts = [dict(row) for row in conn.execute(
            f"SELECT id, quiz_category_id, quiz_title, questions_json, submitted_at FROM exam_attempts "
            f"WHERE username={ph} AND status={ph} ORDER BY submitted_at DESC LIMIT {MAX_ATTEMPTS}",
            (username, "submitted"),
        ).fetchall()]
        if not attempts:
            return {"items": [], "count": 0}
        ids = [a["id"] for a in attempts]
        marks = ",".join([ph] * len(ids))
        results = [dict(row) for row in conn.execute(
            f"SELECT question_id, attempt_id, selected_option, is_correct FROM question_attempt_analytics WHERE attempt_id IN ({marks})",
            tuple(ids),
        ).fetchall()]
    finally:
        conn.close()
    by_attempt: dict[str, dict[str, dict]] = {}
    for row in results:
        by_attempt.setdefault(str(row["attempt_id"]), {})[str(row["question_id"])] = row
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    for attempt in attempts:  # newest first: the first sighting of a question is its latest result
        graded = by_attempt.get(str(attempt["id"]), {})
        for question in repo.json_load(attempt.get("questions_json"), []):
            if not isinstance(question, dict):
                continue
            qid = str(question.get("id") or "")
            row = graded.get(qid)
            if not qid or qid in seen or row is None:
                continue
            seen.add(qid)
            if bool(row.get("is_correct")) or str(question.get("questionType") or "") == "essay":
                continue
            safe = grading.review_question(question)
            items.append({
                "questionId": qid,
                "quizCategoryId": str(attempt.get("quiz_category_id") or ""),
                "quizTitle": str(attempt.get("quiz_title") or ""),
                "submittedAt": str(attempt.get("submitted_at") or ""),
                "question": str(question.get("question") or "")[:2000],
                "questionType": str(question.get("questionType") or "choice"),
                "options": safe.get("options") if isinstance(safe.get("options"), list) else [],
                "yourAnswer": grading.display_answer(question, _selected(row.get("selected_option"))),
                "reviewSource": safe.get("reviewSource") or {},
            })
            if len(items) >= MAX_ITEMS:
                break
    return {"items": items, "count": len(items)}


def _selected(value: Any) -> Any:
    text = str(value if value is not None else "").strip()
    if text.startswith("["):
        return repo.json_load(text, [])
    return text if text else None
