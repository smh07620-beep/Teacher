"""Server-authoritative exam attempts for Teacher 6.3.

The legacy browser exam rendered answer keys and calculated scores in JavaScript.
This extension keeps the existing authoring/admin APIs intact while moving learner
question selection, answer checking and record creation to the server.
"""
from __future__ import annotations

import datetime as _dt
import json
import random
import uuid
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from flask import jsonify, request


QUESTION_TYPES = ("choice", "multi", "true_false", "fill", "essay", "image", "video")
ATTEMPT_TTL_HOURS = 24


def utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _ph(kind: str) -> str:
    return "%s" if kind == "postgres" else "?"


def _json_load(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return default


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _role(base, user: Optional[Dict[str, Any]]) -> str:
    return base.normalize_role((user or {}).get("role", "student"))


def _auth(base):
    user = base._current_user()
    if not user:
        return None, (jsonify({"error": "請先登入後再進行考核。", "loginRequired": True}), 401)
    return user, None


@contextmanager
def _transaction(conn, kind: str):
    if kind == "postgres":
        with conn.transaction():
            yield
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()


def _sanitize_answer_config(config: Any) -> Dict[str, Any]:
    cfg = dict(config) if isinstance(config, dict) else {}
    for key in ("correctIndices", "acceptedAnswers", "correct", "answer", "answers", "solution"):
        cfg.pop(key, None)
    return cfg


def sanitize_question(question: Dict[str, Any]) -> Dict[str, Any]:
    """Return a learner-safe question without answer keys or explanations."""
    q = dict(question or {})
    q.pop("correct", None)
    q.pop("explanation", None)
    q.pop("correctIndices", None)
    q.pop("acceptedAnswers", None)
    q["answerConfig"] = _sanitize_answer_config(q.get("answerConfig"))
    return q


def _answer_has_value(value: Any) -> bool:
    if isinstance(value, list):
        return bool(value)
    return value is not None and str(value).strip() != ""


def _normalize_indices(value: Any) -> List[int]:
    if not isinstance(value, list):
        return []
    out: List[int] = []
    for item in value:
        try:
            idx = int(item)
        except (TypeError, ValueError):
            continue
        if idx not in out:
            out.append(idx)
    return sorted(out)


def score_question(question: Dict[str, Any], answer: Any) -> Optional[bool]:
    """Return True/False for auto-graded questions and None for essays."""
    qtype = str(question.get("questionType") or "choice")
    cfg = question.get("answerConfig") if isinstance(question.get("answerConfig"), dict) else {}
    if qtype == "essay":
        return None
    if qtype == "multi":
        return _normalize_indices(cfg.get("correctIndices", [])) == _normalize_indices(answer)
    if qtype == "fill":
        case_sensitive = bool(cfg.get("caseSensitive", False))
        actual = str(answer or "").strip()
        if not case_sensitive:
            actual = actual.casefold()
        for candidate in cfg.get("acceptedAnswers", []) or []:
            expected = str(candidate or "").strip()
            if not case_sensitive:
                expected = expected.casefold()
            if actual == expected:
                return True
        return False
    try:
        return int(answer) == int(question.get("correct", -999999))
    except (TypeError, ValueError):
        return False


def _display_answer(question: Dict[str, Any], answer: Any) -> str:
    qtype = str(question.get("questionType") or "choice")
    options = question.get("options") if isinstance(question.get("options"), list) else []
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if not _answer_has_value(answer):
        return "未答"
    if qtype in {"essay", "fill"}:
        return _text(answer, 12000)
    if qtype == "multi":
        values = _normalize_indices(answer)
        return "、".join(letters[i] if 0 <= i < len(letters) else str(i + 1) for i in values)
    try:
        idx = int(answer)
    except (TypeError, ValueError):
        return "未答"
    if qtype == "true_false" and 0 <= idx < len(options):
        return _text(options[idx], 200)
    return letters[idx] if 0 <= idx < len(letters) else str(idx + 1)


def _draw_questions(base, category: Dict[str, Any]) -> List[Dict[str, Any]]:
    category_id = str(category.get("id") or "")
    questions = [dict(q) for q in base.list_quiz_questions(category_id) if q.get("active", True)]
    draw_rules = category.get("drawRules") if isinstance(category.get("drawRules"), dict) else {}
    if draw_rules.get("mode") == "type_quota":
        quotas = draw_rules.get("quotas") if isinstance(draw_rules.get("quotas"), dict) else {}
        target = sum(max(0, int(quotas.get(t, 0) or 0)) for t in QUESTION_TYPES)
        selected: List[Dict[str, Any]] = []
        selected_ids = set()
        for qtype in QUESTION_TYPES:
            pool = [q for q in questions if str(q.get("questionType") or "choice") == qtype]
            random.shuffle(pool)
            want = max(0, int(quotas.get(qtype, 0) or 0))
            for q in pool[: min(want, len(pool))]:
                selected.append(q)
                selected_ids.add(str(q.get("id")))
        if len(selected) < target:
            remaining = [q for q in questions if str(q.get("id")) not in selected_ids]
            random.shuffle(remaining)
            selected.extend(remaining[: max(0, target - len(selected))])
        random.shuffle(selected)
        return selected
    random.shuffle(questions)
    try:
        count = max(0, int(category.get("drawCount", 0) or 0))
    except (TypeError, ValueError):
        count = 0
    return questions if count <= 0 else questions[: min(count, len(questions))]


def _public_review_question(question: Dict[str, Any]) -> Dict[str, Any]:
    q = dict(question or {})
    q["answerConfig"] = dict(q.get("answerConfig")) if isinstance(q.get("answerConfig"), dict) else {}
    return q


def _attempt_expired(started_at: str) -> bool:
    try:
        started = _dt.datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
        if started.tzinfo is None:
            started = started.replace(tzinfo=_dt.timezone.utc)
        return _dt.datetime.now(_dt.timezone.utc) - started > _dt.timedelta(hours=ATTEMPT_TTL_HOURS)
    except Exception:
        return True


def init_exam_integrity_db(base) -> None:
    conn, _kind = base._db_conn()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS exam_attempts (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                emp_id TEXT NOT NULL DEFAULT '',
                quiz_category_id TEXT NOT NULL,
                quiz_title TEXT NOT NULL DEFAULT '',
                group_key TEXT NOT NULL DEFAULT 'grpBio',
                training_area TEXT NOT NULL DEFAULT 'internal',
                course_id TEXT NOT NULL DEFAULT '',
                passing_score INTEGER NOT NULL DEFAULT 80,
                publication_id TEXT NOT NULL DEFAULT '',
                publication_hash TEXT NOT NULL DEFAULT '',
                questions_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'started',
                record_id TEXT NOT NULL DEFAULT '',
                started_at TEXT NOT NULL,
                submitted_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_exam_attempts_user ON exam_attempts(username, status, started_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_exam_attempts_category ON exam_attempts(quiz_category_id, status, started_at)")
    finally:
        conn.close()


def _get_attempt(conn, kind: str, attempt_id: str):
    ph = _ph(kind)
    return conn.execute(f"SELECT * FROM exam_attempts WHERE id={ph}", (attempt_id,)).fetchone()


def _attempt_response(row) -> Dict[str, Any]:
    raw = dict(row)
    questions = _json_load(raw.get("questions_json"), [])
    return {
        "attemptId": str(raw.get("id", "")),
        "status": str(raw.get("status", "started")),
        "quizCategoryId": str(raw.get("quiz_category_id", "")),
        "quizTitle": str(raw.get("quiz_title", "")),
        "group": str(raw.get("group_key", "")),
        "area": str(raw.get("training_area", "")),
        "courseId": str(raw.get("course_id", "")),
        "passingScore": int(raw.get("passing_score", 80) or 80),
        "startedAt": str(raw.get("started_at", "")),
        "questions": [sanitize_question(dict(q)) for q in questions if isinstance(q, dict)],
    }


def _insert_exam_record(conn, kind: str, base, user: Dict[str, Any], attempt: Dict[str, Any], answers_detail: List[Dict[str, Any]],
                        score: int, status: str, correct_count: int, wrong_count: int, evaluator_name: str,
                        evaluator_title: str, examinee_role: str, submitted_at: str) -> str:
    ph = _ph(kind)
    record_id = f"attempt-{attempt['id']}"[:100]
    review_status = "pending" if any(a.get("questionType") == "essay" for a in answers_detail) else "completed"
    sql = f"""
        INSERT INTO exam_records
        (id, created_at, name, emp_id, role, evaluator_name, evaluator_title, quiz_title,
         score, status, correct_count, wrong_count, answers_detail, group_key, training_area,
         course_id, review_status, quiz_category_id, passing_score, publication_id, publication_hash)
        VALUES ({','.join([ph] * 21)})
    """
    values = (
        record_id, submitted_at, _text(user.get("name"), 100), _text(user.get("empId") or user.get("emp_id"), 100),
        _text(examinee_role or _role(base, user), 100), evaluator_name, evaluator_title,
        _text(attempt.get("quiz_title"), 255), int(score), _text(status, 30), int(correct_count), int(wrong_count),
        _json_dump(answers_detail), _text(attempt.get("group_key"), 100), _text(attempt.get("training_area"), 30),
        _text(attempt.get("course_id"), 100), review_status, _text(attempt.get("quiz_category_id"), 100),
        int(attempt.get("passing_score", 80) or 80), _text(attempt.get("publication_id"), 100), _text(attempt.get("publication_hash"), 64),
    )
    conn.execute(sql, values)
    return record_id


def register_exam_integrity(base):
    app = base.app
    if app.extensions.get("exam_integrity_registered"):
        return app
    init_exam_integrity_db(base)
    app.extensions["exam_integrity_registered"] = True

    @app.before_request
    def reject_legacy_client_scoring():
        if request.path == "/api/records" and request.method == "POST":
            user = base._current_user()
            if user and _role(base, user) not in {"education_admin", "system_admin"}:
                return jsonify({"error": "此版本已改由伺服器計分，請重新整理考核頁後再提交。", "secureExamRequired": True}), 409
        return None

    @app.after_request
    def remove_answer_keys_from_learner_question_api(response):
        try:
            if request.method != "GET" or request.path not in {"/api/quiz-questions", "/api/quiz-questions/random"}:
                return response
            user = base._current_user()
            if user and _role(base, user) in {"education_admin", "system_admin"}:
                return response
            if response.status_code != 200 or not str(response.content_type or "").startswith("application/json"):
                return response
            data = response.get_json(silent=True)
            if not isinstance(data, list):
                return response
            response.set_data(_json_dump([sanitize_question(dict(q)) for q in data if isinstance(q, dict)]))
            response.content_type = "application/json; charset=utf-8"
        except Exception:
            return response
        return response

    @app.post("/api/exam-attempts")
    def exam_attempt_start():
        user, denied = _auth(base)
        if denied:
            return denied
        data = request.get_json(silent=True) or {}
        category_id = _text(data.get("quizCategoryId") or data.get("categoryId"), 100)
        if not category_id:
            return jsonify({"error": "缺少考卷識別碼。"}), 400
        category = base.get_quiz_category(category_id)
        if not category or not category.get("active", True):
            return jsonify({"error": "找不到可使用的考卷。"}), 404
        questions = _draw_questions(base, category)
        if not questions:
            return jsonify({"error": "此考卷目前沒有可作答的啟用題目。"}), 409
        attempt_id = uuid.uuid4().hex
        now = utcnow()
        try:
            passing_score = max(1, min(100, int(category.get("passingScore", 80) or 80)))
        except (TypeError, ValueError):
            passing_score = 80
        conn, kind = base._db_conn(); ph = _ph(kind)
        try:
            conn.execute(
                f"INSERT INTO exam_attempts (id,username,emp_id,quiz_category_id,quiz_title,group_key,training_area,course_id,passing_score,publication_id,publication_hash,questions_json,status,record_id,started_at,submitted_at) VALUES ({','.join([ph] * 16)})",
                (attempt_id, _text(user.get("username"), 100).lower(), _text(user.get("empId") or user.get("emp_id"), 100),
                 category_id, _text(category.get("title") or "考卷", 255), _text(category.get("group") or "grpBio", 100),
                 _text(category.get("area") or "internal", 30), _text(category.get("courseId"), 100), passing_score,
                 _text(category.get("publicationId"), 100), _text(category.get("publicationHash"), 64), _json_dump(questions),
                 "started", "", now, ""),
            )
            row = _get_attempt(conn, kind, attempt_id)
            return jsonify(_attempt_response(row)), 201
        finally:
            conn.close()

    @app.get("/api/exam-attempts/<attempt_id>")
    def exam_attempt_resume(attempt_id):
        user, denied = _auth(base)
        if denied:
            return denied
        conn, kind = base._db_conn()
        try:
            row = _get_attempt(conn, kind, _text(attempt_id, 100))
            if not row:
                return jsonify({"error": "找不到此考核作答。"}), 404
            raw = dict(row)
            if str(raw.get("username", "")) != _text(user.get("username"), 100).lower():
                return jsonify({"error": "此考核作答不屬於目前登入者。"}), 403
            if str(raw.get("status")) != "started":
                return jsonify({"error": "此考核已經提交。", "submitted": True}), 409
            if _attempt_expired(str(raw.get("started_at", ""))):
                return jsonify({"error": "此考核作答已超過 24 小時，請重新開始。", "expired": True}), 410
            return jsonify(_attempt_response(row))
        finally:
            conn.close()

    @app.post("/api/exam-attempts/<attempt_id>/submit")
    def exam_attempt_submit(attempt_id):
        user, denied = _auth(base)
        if denied:
            return denied
        data = request.get_json(silent=True) or {}
        raw_answers = data.get("answers")
        if not isinstance(raw_answers, list):
            return jsonify({"error": "作答資料格式不正確。"}), 400
        evaluator_name = _text(data.get("evaluatorName"), 100)
        evaluator_title = _text(data.get("evaluatorTitle"), 100)
        examinee_role = _text(data.get("examineeRole"), 100)
        if not evaluator_name or not evaluator_title:
            return jsonify({"error": "請填寫考核人員姓名與職稱。"}), 400
        conn, kind = base._db_conn(); ph = _ph(kind)
        try:
            with _transaction(conn, kind):
                row = _get_attempt(conn, kind, _text(attempt_id, 100))
                if not row:
                    return jsonify({"error": "找不到此考核作答。"}), 404
                attempt = dict(row)
                if str(attempt.get("username", "")) != _text(user.get("username"), 100).lower():
                    return jsonify({"error": "此考核作答不屬於目前登入者。"}), 403
                if str(attempt.get("status")) != "started":
                    return jsonify({"error": "此考核已經提交，不能重複計分。"}), 409
                if _attempt_expired(str(attempt.get("started_at", ""))):
                    return jsonify({"error": "此考核作答已超過 24 小時，請重新開始。"}), 410
                questions = [dict(q) for q in _json_load(attempt.get("questions_json"), []) if isinstance(q, dict)]
                if len(raw_answers) != len(questions):
                    return jsonify({"error": "作答題數與伺服器考卷不一致，請重新整理。"}), 409
                answers_detail: List[Dict[str, Any]] = []
                correct_count = wrong_count = essay_count = 0
                category_stats: Dict[str, Dict[str, int]] = {}
                for index, question in enumerate(questions):
                    answer = raw_answers[index]
                    qtype = str(question.get("questionType") or "choice")
                    result = score_question(question, answer)
                    tag = _text(question.get("tag") or "一般", 100)
                    answers_detail.append({"num": index + 1, "questionText": _text(question.get("question"), 5000),
                                           "questionType": qtype, "userAnswer": _display_answer(question, answer), "isCorrect": result})
                    if qtype == "essay":
                        essay_count += 1
                        continue
                    stats = category_stats.setdefault(tag, {"total": 0, "correct": 0})
                    stats["total"] += 1
                    if result is True:
                        correct_count += 1; stats["correct"] += 1
                    else:
                        wrong_count += 1
                total = len(questions)
                score = round((correct_count / total) * 100) if total else 0
                passing_score = max(1, min(100, int(attempt.get("passing_score", 80) or 80)))
                status = "待人工批改" if essay_count else ("合格" if score >= passing_score else "未達標")
                submitted_at = utcnow()
                record_id = _insert_exam_record(conn, kind, base, user, attempt, answers_detail, score, status,
                                                correct_count, wrong_count, evaluator_name, evaluator_title,
                                                examinee_role, submitted_at)
                cur = conn.execute(
                    f"UPDATE exam_attempts SET status={ph}, record_id={ph}, submitted_at={ph} WHERE id={ph} AND status={ph}",
                    ("submitted", record_id, submitted_at, attempt["id"], "started"),
                )
                if getattr(cur, "rowcount", 1) != 1:
                    raise RuntimeError("考核狀態已由其他請求更新，請重新整理。")
            return jsonify({"ok": True, "attemptId": attempt["id"], "recordId": record_id, "score": score,
                            "status": status, "correctCount": correct_count, "wrongCount": wrong_count,
                            "essayCount": essay_count, "passingScore": passing_score, "categoryStats": category_stats,
                            "questions": [_public_review_question(q) for q in questions], "submittedAt": submitted_at})
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 409
        finally:
            conn.close()

    return app
