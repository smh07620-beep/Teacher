"""Exam attempt orchestration and server-authoritative submission rules."""

from __future__ import annotations

import datetime as dt
import random
import uuid
from typing import Any, Mapping

from teacher_app.common.errors import ApiError
from teacher_app.exams import grading
from teacher_app.exams import repository as repo

QUESTION_TYPES = ("choice", "multi", "true_false", "fill", "essay", "image", "video")
ATTEMPT_TTL_HOURS = 24


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _username(user: Mapping[str, Any]) -> str:
    return _text(user.get("username"), 100).lower()


def _role(base, user: Mapping[str, Any]) -> str:
    return base.normalize_role(user.get("role", "student"))


def require_user(user: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not user:
        raise ApiError("LOGIN_REQUIRED", "請先登入後再進行考核。", 401, {"loginRequired": True})
    return user


def _draw_questions(base, category: Mapping[str, Any]) -> list[dict[str, Any]]:
    category_id = str(category.get("id") or "")
    questions = [dict(q) for q in base.list_quiz_questions(category_id) if q.get("active", True)]
    draw_rules = category.get("drawRules") if isinstance(category.get("drawRules"), dict) else {}
    if draw_rules.get("mode") == "type_quota":
        quotas = draw_rules.get("quotas") if isinstance(draw_rules.get("quotas"), dict) else {}
        target = sum(max(0, int(quotas.get(question_type, 0) or 0)) for question_type in QUESTION_TYPES)
        selected: list[dict[str, Any]] = []
        selected_ids: set[str] = set()
        for question_type in QUESTION_TYPES:
            pool = [q for q in questions if str(q.get("questionType") or "choice") == question_type]
            random.shuffle(pool)
            for question in pool[:min(max(0, int(quotas.get(question_type, 0) or 0)), len(pool))]:
                selected.append(question)
                selected_ids.add(str(question.get("id")))
        if len(selected) < target:
            remaining = [q for q in questions if str(q.get("id")) not in selected_ids]
            random.shuffle(remaining)
            selected.extend(remaining[:max(0, target - len(selected))])
        random.shuffle(selected)
        return selected
    random.shuffle(questions)
    try:
        count = max(0, int(category.get("drawCount", 0) or 0))
    except (TypeError, ValueError):
        count = 0
    return questions if count <= 0 else questions[:min(count, len(questions))]


def _expired(started_at: str) -> bool:
    try:
        started = dt.datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
        if started.tzinfo is None:
            started = started.replace(tzinfo=dt.timezone.utc)
        return dt.datetime.now(dt.timezone.utc) - started > dt.timedelta(hours=ATTEMPT_TTL_HOURS)
    except Exception:
        return True


def attempt_response(attempt: Mapping[str, Any]) -> dict[str, Any]:
    questions = repo.json_load(attempt.get("questions_json"), [])
    return {
        "attemptId": str(attempt.get("id", "")), "status": str(attempt.get("status", "started")),
        "quizCategoryId": str(attempt.get("quiz_category_id", "")), "quizTitle": str(attempt.get("quiz_title", "")),
        "group": str(attempt.get("group_key", "")), "area": str(attempt.get("training_area", "")),
        "courseId": str(attempt.get("course_id", "")), "passingScore": int(attempt.get("passing_score", 80) or 80),
        "startedAt": str(attempt.get("started_at", "")),
        "questions": [grading.sanitize_question(q) for q in questions if isinstance(q, dict)],
    }


def start_attempt(base, user: Mapping[str, Any] | None, data: Mapping[str, Any]) -> dict[str, Any]:
    actor = require_user(user)
    category_id = _text(data.get("quizCategoryId") or data.get("categoryId"), 100)
    if not category_id:
        raise ApiError("CATEGORY_REQUIRED", "缺少考卷識別碼。", 400)
    category = base.get_quiz_category(category_id)
    if not category or not category.get("active", True):
        raise ApiError("CATEGORY_NOT_FOUND", "找不到可使用的考卷。", 404)
    questions = _draw_questions(base, category)
    if not questions:
        raise ApiError("NO_ACTIVE_QUESTIONS", "此考卷目前沒有可作答的啟用題目。", 409)
    try:
        passing_score = max(1, min(100, int(category.get("passingScore", 80) or 80)))
    except (TypeError, ValueError):
        passing_score = 80
    attempt = {
        "id": uuid.uuid4().hex, "username": _username(actor),
        "emp_id": _text(actor.get("empId") or actor.get("emp_id"), 100), "quiz_category_id": category_id,
        "quiz_title": _text(category.get("title") or "考卷", 255), "group_key": _text(category.get("group") or "grpBio", 100),
        "training_area": _text(category.get("area") or "internal", 30), "course_id": _text(category.get("courseId"), 100),
        "passing_score": passing_score, "publication_id": _text(category.get("publicationId"), 100),
        "publication_hash": _text(category.get("publicationHash"), 64), "questions_json": repo.json_dump(questions),
        "status": "started", "record_id": "", "started_at": utcnow(), "submitted_at": "",
    }
    with repo.transaction(base) as (conn, kind):
        repo.create_attempt(conn, kind, attempt)
    return attempt_response(attempt)


def _owned_started_attempt(conn, kind: str, user: Mapping[str, Any], attempt_id: str, *, submitting: bool = False) -> dict[str, Any]:
    attempt = repo.get_attempt(conn, kind, _text(attempt_id, 100))
    if not attempt:
        raise ApiError("ATTEMPT_NOT_FOUND", "找不到此考核作答。", 404)
    if str(attempt.get("username", "")) != _username(user):
        raise ApiError("ATTEMPT_FORBIDDEN", "此考核作答不屬於目前登入者。", 403)
    if str(attempt.get("status")) != "started":
        message = "此考核已經提交，不能重複計分。" if submitting else "此考核已經提交。"
        extra = {} if submitting else {"submitted": True}
        raise ApiError("ATTEMPT_SUBMITTED", message, 409, extra)
    if _expired(str(attempt.get("started_at", ""))):
        raise ApiError("ATTEMPT_EXPIRED", "此考核作答已超過 24 小時，請重新開始。", 410, {"expired": True})
    return attempt


def resume_attempt(base, user: Mapping[str, Any] | None, attempt_id: str) -> dict[str, Any]:
    actor = require_user(user)
    conn, kind = base._db_conn()
    try:
        return attempt_response(_owned_started_attempt(conn, kind, actor, attempt_id))
    finally:
        conn.close()


def submit_attempt(base, user: Mapping[str, Any] | None, attempt_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
    actor = require_user(user)
    answers = data.get("answers")
    if not isinstance(answers, list):
        raise ApiError("INVALID_ANSWERS", "作答資料格式不正確。", 400)
    evaluator_name = _text(data.get("evaluatorName"), 100)
    evaluator_title = _text(data.get("evaluatorTitle"), 100)
    examinee_role = _text(data.get("examineeRole"), 100) or _text(_role(base, actor), 100)
    if not evaluator_name or not evaluator_title:
        raise ApiError("EVALUATOR_REQUIRED", "請填寫考核人員姓名與職稱。", 400)
    try:
        with repo.transaction(base) as (conn, kind):
            attempt = _owned_started_attempt(conn, kind, actor, attempt_id, submitting=True)
            questions = [dict(q) for q in repo.json_load(attempt.get("questions_json"), []) if isinstance(q, dict)]
            if len(answers) != len(questions):
                raise ApiError("ANSWER_COUNT_MISMATCH", "作答題數與伺服器考卷不一致，請重新整理。", 409)
            passing_score = max(1, min(100, int(attempt.get("passing_score", 80) or 80)))
            result = grading.grade_attempt(questions, answers, passing_score)
            submitted_at = utcnow()
            record_id = f"attempt-{attempt['id']}"[:100]
            repo.mark_submitted(conn, kind, str(attempt["id"]), record_id, submitted_at)
            repo.insert_exam_record(
                conn, kind, record_id=record_id, user=actor, attempt=attempt,
                answers_detail=result["answersDetail"], score=result["score"], status=result["status"],
                correct_count=result["correctCount"], wrong_count=result["wrongCount"],
                evaluator_name=evaluator_name, evaluator_title=evaluator_title, examinee_role=examinee_role,
                submitted_at=submitted_at,
            )
    except repo.AttemptConflict as exc:
        raise ApiError("ATTEMPT_CONFLICT", str(exc), 409) from exc
    return {
        "ok": True, "attemptId": str(attempt["id"]), "recordId": record_id, "score": result["score"],
        "status": result["status"], "correctCount": result["correctCount"], "wrongCount": result["wrongCount"],
        "essayCount": result["essayCount"], "passingScore": passing_score, "categoryStats": result["categoryStats"],
        "questions": [dict(question) for question in questions], "submittedAt": submitted_at,
    }
