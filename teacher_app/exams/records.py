"""Canonical exam-record persistence and manual-review behavior."""
from __future__ import annotations

import datetime as dt
import json
from typing import Any, Mapping

from teacher_app.assessments import repository as assessment_repository
from teacher_app.common import audit
from teacher_app.common import db as common_db
from teacher_app.common import scope
from teacher_app.common.auth import has_permission, user_roles
from teacher_app.learning.progress_service import record_to_dict


class RecordError(ValueError):
    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.status = status


def list_records() -> list[dict]:
    with common_db.read_connection() as (conn, _kind):
        rows = conn.execute("SELECT * FROM exam_records ORDER BY created_at DESC").fetchall()
    return [record_to_dict(row) for row in rows]


def category_review_summary(category_ids: list[str]) -> dict[str, dict[str, int]]:
    ids = [str(value or "").strip()[:100] for value in category_ids if str(value or "").strip()]
    if not ids:
        return {}
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        marks = ",".join([ph] * len(ids))
        rows = conn.execute(
            f"SELECT quiz_category_id,review_status,COUNT(*) AS cnt FROM exam_records "
            f"WHERE quiz_category_id IN ({marks}) GROUP BY quiz_category_id,review_status",
            tuple(ids),
        ).fetchall()
    summary: dict[str, dict[str, int]] = {value: {"pending": 0, "completed": 0, "total": 0} for value in ids}
    for row in rows:
        mapped = dict(row)
        category_id = str(mapped.get("quiz_category_id") or "")
        status = str(mapped.get("review_status") or "completed")
        count = int(mapped.get("cnt", 0) or 0)
        bucket = summary.setdefault(category_id, {"pending": 0, "completed": 0, "total": 0})
        bucket["total"] += count
        if status == "pending":
            bucket["pending"] += count
        else:
            bucket["completed"] += count
    return summary


def clear_records() -> None:
    with common_db.transaction() as (conn, _kind):
        conn.execute("DELETE FROM exam_records")


def _reviewer_identity(reviewer_user: Mapping[str, Any] | None) -> tuple[str, str]:
    if not reviewer_user:
        raise RecordError("無法確認批改者登入身分", 401)
    reviewer = str(
        reviewer_user.get("name")
        or reviewer_user.get("displayName")
        or reviewer_user.get("username")
        or ""
    ).strip()[:100]
    reviewer_title = str(
        reviewer_user.get("title")
        or reviewer_user.get("jobTitle")
        or reviewer_user.get("position")
        or ""
    ).strip()[:100]
    if not reviewer:
        raise RecordError("批改者帳號缺少可辨識姓名", 400)
    return reviewer, reviewer_title


def _username(value: Any) -> str:
    return str(value or "").strip().lower()[:100]


def _table_exists(conn, kind: str, table: str) -> bool:
    if kind == "postgres":
        return bool(conn.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema=current_schema() AND table_name=%s",
            (table,),
        ).fetchone())
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone())


def _review_scope(conn, kind: str, reviewer_user: Mapping[str, Any], record: Mapping[str, Any]) -> str:
    """Resolve the authoritative scope that permits this review, or fail closed."""
    roles = set(user_roles(reviewer_user))
    target_group = scope.normalize_group(record.get("groupKey") or record.get("group_key"))
    reviewer_group = scope.normalize_group(
        reviewer_user.get("preferredGroup") or reviewer_user.get("preferred_group")
    )

    # A group leader's authority is strictly bounded to the authenticated
    # account's own group. Browser-supplied record/group fields are irrelevant.
    if "group_leader" in roles and target_group == reviewer_group:
        return "group"

    if "clinical_teacher" not in roles:
        raise RecordError("此帳號不在這筆考核紀錄的批改範圍內", 403)

    # A clinical teacher may receive group-level access only through an actual
    # server permission. The default clinical_teacher role does not have it.
    if has_permission(reviewer_user, "student.view_group") and target_group == reviewer_group:
        return "group_permission"

    teacher_username = _username(reviewer_user.get("username"))
    target_emp_id = str(record.get("empId") or record.get("emp_id") or "").strip()[:100]
    if not teacher_username or not target_emp_id:
        raise RecordError("無法確認此考核紀錄的教師指派範圍", 403)
    if not _table_exists(conn, kind, "user_accounts") or not _table_exists(conn, kind, "pgy_assignments"):
        raise RecordError("無法確認此考核紀錄的教師指派範圍", 403)

    ph = common_db.placeholder(kind)
    learner = conn.execute(
        f"SELECT username FROM user_accounts WHERE emp_id={ph}",
        (target_emp_id,),
    ).fetchone()
    if not learner:
        raise RecordError("找不到此考核紀錄對應的學員帳號", 403)
    learner_username = _username(dict(learner).get("username"))
    assignment = conn.execute(
        f"SELECT 1 FROM pgy_assignments "
        f"WHERE learner_username={ph} AND teacher_username={ph} "
        "AND status<>'cancelled' LIMIT 1",
        (learner_username, teacher_username),
    ).fetchone()
    if not assignment:
        raise RecordError("此學員未指派給目前登入的臨床教師", 403)
    return "assigned_student"


def can_review_record(
    reviewer_user: Mapping[str, Any] | None,
    record: Mapping[str, Any] | None,
) -> bool:
    """Return whether the authenticated reviewer may act on this record.

    Read projections (teacher queues, notifications and email reminders) use the
    same fail-closed resource scope as the write endpoint so an unassigned
    teacher never sees a review item that the backend would later reject.
    """
    if not reviewer_user or not record or not has_permission(reviewer_user, "evaluation.review"):
        return False
    try:
        with common_db.read_connection() as (conn, kind):
            _review_scope(conn, kind, reviewer_user, record)
        return True
    except (RecordError, Exception):
        return False


def review_record(
    record_id: str,
    data: Mapping[str, Any],
    *,
    reviewer_user: Mapping[str, Any] | None,
) -> dict:
    scores = data.get("essayScores", {}) if isinstance(data.get("essayScores", {}), dict) else {}
    reviewer, reviewer_title = _reviewer_identity(reviewer_user)
    comment = str(data.get("reviewComment", "")).strip()[:2000]
    scope_kind = ""
    target_group = ""
    target_emp_id = ""
    final_score = 0
    status = ""
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(f"SELECT * FROM exam_records WHERE id={ph}", (record_id,)).fetchone()
        if not row:
            raise RecordError("找不到考試紀錄", 404)
        record = record_to_dict(row)
        scope_kind = _review_scope(conn, kind, reviewer_user or {}, record)
        target_group = scope.normalize_group(record.get("groupKey"))
        target_emp_id = str(record.get("empId") or "")[:100]
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
                answer["reviewerTitle"] = reviewer_title
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
    audit.record_event(
        actor=reviewer_user,
        action="exam.record.review",
        target_type="exam_record",
        target_id=record_id,
        group=target_group,
        scope={"kind": scope_kind, "empId": target_emp_id},
        after={"score": final_score, "status": status, "reviewStatus": "completed"},
    )
    return {
        "ok": True,
        "score": final_score,
        "status": status,
        "reviewerName": reviewer,
        "reviewerTitle": reviewer_title,
    }


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
    group_key = scope.normalize_group(values.get("groupKey", scope.DEFAULT_GROUP))
    training_area = scope.normalize_area(values.get("trainingArea", scope.DEFAULT_TRAINING_AREA))
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


__all__ = ["RecordError", "can_review_record", "category_review_summary", "clear_records", "create_record", "list_records", "review_record"]