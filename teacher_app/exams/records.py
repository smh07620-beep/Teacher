"""Canonical exam-record persistence and manual-review behavior."""
from __future__ import annotations

import datetime as dt
import json
from typing import Any, Mapping

from teacher_app.assessments import repository as assessment_repository
from teacher_app.common import db as common_db
from teacher_app.common import scope
from teacher_app.learning.progress_service import record_to_dict


class RecordError(ValueError):
    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.status = status


def list_records() -> list[dict]:
    with common_db.read_connection() as (conn, _kind):
        rows = conn.execute("SELECT * FROM exam_records ORDER BY created_at DESC").fetchall()
    return [record_to_dict(row) for row in rows]


def clear_records() -> None:
    with common_db.transaction() as (conn, _kind):
        conn.execute("DELETE FROM exam_records")


def review_record(record_id: str, data: Mapping[str, Any]) -> dict:
    scores = data.get("essayScores", {}) if isinstance(data.get("essayScores", {}), dict) else {}
    reviewer = str(data.get("reviewerName", "")).strip()[:100]
    if not reviewer:
        raise RecordError("問答題批改必須填寫批改者姓名", 400)
    comment = str(data.get("reviewComment", "")).strip()[:2000]
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(f"SELECT * FROM exam_records WHERE id={ph}", (record_id,)).fetchone()
        if not row:
            raise RecordError("找不到考試紀錄", 404)
        record = record_to_dict(row)
        answers = record.get("answersDetail", [])
        if not answers:
            raise RecordError("此紀錄沒有題目明細", 400)
        reviewed_at = dt.datetime.now(dt.timezone.utc).isoformat()
        points = 0.0
        for index, answer in enumerate(answers):
            if answer.get("questionType") == "essay":
                if str(index) not in scores and index not in scores:
                    raise RecordError(f"第 {index + 1} 題問答題尚未逐題給分", 400)
                raw = scores.get(str(index), scores.get(index))
                if raw in (None, ""):
                    raise RecordError(f"第 {index + 1} 題問答題尚未逐題給分", 400)
                try:
                    grade = max(0.0, min(100.0, float(raw)))
                except (TypeError, ValueError) as exc:
                    raise RecordError(f"第 {index + 1} 題問答題分數格式錯誤", 400) from exc
                answer["reviewScore"] = grade
                answer["reviewComment"] = str((data.get("essayComments") or {}).get(str(index), ""))[:1000]
                answer["reviewerName"] = reviewer
                answer["reviewedAt"] = reviewed_at
                points += grade / 100.0
            else:
                points += 1.0 if answer.get("isCorrect") is True else 0.0
        final_score = round(points / len(answers) * 100)
        passing_score = max(1, min(100, int(record.get("passingScore", 80) or 80)))
        status = "合格" if final_score >= passing_score else "未達標"
        payload = json.dumps(answers, ensure_ascii=False)
        answers_expr = "%s::jsonb" if kind == "postgres" else "?"
        conn.execute(
            f"UPDATE exam_records SET score={ph},status={ph},answers_detail={answers_expr},"
            f"review_status='completed',reviewed_at={ph},reviewer_name={ph},review_comment={ph} WHERE id={ph}",
            (final_score, status, payload, reviewed_at, reviewer, comment, record_id),
        )
    return {"ok": True, "score": final_score, "status": status}


def create_record(user: Mapping[str, Any], data: Mapping[str, Any]) -> str:
    values = dict(data)
    values["name"] = user.get("name", "")
    values["empId"] = user.get("empId", "")
    required = ["id", "name", "empId", "role", "quizTitle", "score", "status"]
    missing = [key for key in required if values.get(key) in (None, "")]
    if missing:
        raise RecordError(f"缺少欄位：{', '.join(missing)}", 400)
    try:
        score = max(0, min(100, int(values.get("score", 0))))
        correct_count = int(values.get("correctCount", 0))
        wrong_count = int(values.get("wrongCount", 0))
    except (TypeError, ValueError) as exc:
        raise RecordError("分數或題數格式錯誤", 400) from exc

    record_id = str(values["id"])[:100]
    created_at = dt.datetime.now(dt.timezone.utc).isoformat()
    answers = values.get("answersDetail", [])
    try:
        group_key = scope.validate_group(
            values.get("groupKey", scope.DEFAULT_GROUP)
        )
        training_area = scope.validate_area(
            values.get("trainingArea", scope.DEFAULT_TRAINING_AREA)
        )
    except ValueError as exc:
        raise RecordError(str(exc), 400) from exc
    course_id = str(values.get("courseId", "")).strip()[:100]
    quiz_category_id = str(values.get("quizCategoryId", "")).strip()[:100]
    # Records snapshot the publication identity that was active when the attempt
    # was submitted.  The compact category projection intentionally omits these
    # fields, so use the full category record here just like the legacy surface.
    publication = assessment_repository.get_category_full(quiz_category_id) if quiz_category_id else None
    publication_id = str((publication or {}).get("publicationId", "") or "")[:100]
    publication_hash = str((publication or {}).get("publicationHash", "") or "")[:64]
    try:
        passing_score = max(1, min(100, int(values.get("passingScore", 80) or 80)))
    except (TypeError, ValueError):
        passing_score = 80
    has_essay = any(isinstance(answer, dict) and answer.get("questionType") == "essay" for answer in answers)
    review_status = "pending" if has_essay else "completed"
    status = "待人工批改" if has_essay else str(values["status"])[:30]
    payload = json.dumps(answers, ensure_ascii=False)

    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        columns = (
            "id", "created_at", "name", "emp_id", "role", "evaluator_name", "evaluator_title",
            "quiz_title", "score", "status", "correct_count", "wrong_count", "answers_detail",
            "group_key", "training_area", "course_id", "review_status", "quiz_category_id",
            "passing_score", "publication_id", "publication_hash",
        )
        raw_values = (
            record_id, created_at, str(values["name"])[:100], str(values["empId"])[:100],
            str(values["role"])[:100], str(values.get("evaluatorName", ""))[:100],
            str(values.get("evaluatorTitle", ""))[:100], str(values["quizTitle"])[:255], score,
            status, correct_count, wrong_count, payload, group_key, training_area, course_id,
            review_status, quiz_category_id, passing_score, publication_id, publication_hash,
        )
        if kind == "postgres":
            placeholders = [ph] * len(columns)
            placeholders[12] = "%s::jsonb"
            conn.execute(
                f"INSERT INTO exam_records ({','.join(columns)}) VALUES ({','.join(placeholders)}) ON CONFLICT (id) DO NOTHING",
                raw_values,
            )
        else:
            conn.execute(
                f"INSERT OR IGNORE INTO exam_records ({','.join(columns)}) VALUES ({','.join([ph] * len(columns))})",
                raw_values,
            )
    return record_id


__all__ = ["RecordError", "clear_records", "create_record", "list_records", "review_record"]
