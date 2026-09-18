"""Question Bank 2.0 HTTP adapter plus deferred blueprint/analytics runtime."""
from __future__ import annotations

import json
import random
import uuid
from collections import Counter

from flask import jsonify, request

from teacher_app.assessments import question_bank as bank_service
from teacher_app.common.errors import ApiError


def _error(exc: ApiError):
    return jsonify({"error": exc.message, **(exc.extra or {})}), exc.status


def _decode(value, fallback):
    try:
        return json.loads(value) if isinstance(value, str) else value
    except Exception:
        return fallback


def permitted(base, capability="question.manage", group=None):
    if not hasattr(base, "require_scoped_permission"):
        return base.require_admin()
    # Question rows use the existing quiz-category assignment for scope.  An
    # absent category is deliberately not widened for a teacher/group leader.
    if group is None:
        body = request.get_json(silent=True) or {}
        category = str(
            request.args.get("quizCategoryId")
            or body.get("quizCategoryId")
            or ""
        ).strip()
        if category:
            quiz = base.get_quiz_category(category)
            group = (quiz or {}).get("group")
    return base.require_scoped_permission(capability, group)


def _draw(rows, count, quotas, excluded=()):
    """Find one single exact-sized set satisfying all quota dimensions."""
    rows = [row for row in rows if row["id"] not in set(excluded)]
    if count < 1 or len(rows) < count:
        raise ValueError("已審核題目不足以建立 blueprint")
    requirements = []
    for field in ("topic", "difficulty", "cognitive_level"):
        requested = quotas.get(field, {})
        if not isinstance(requested, dict):
            raise ValueError("quota 格式錯誤")
        for value, amount in requested.items():
            amount = int(amount or 0)
            if amount < 0 or amount > count:
                raise ValueError("quota 數量無效")
            if amount:
                requirements.append((field, str(value), amount))
    random.shuffle(rows)
    suffix = [[0] * len(requirements) for _ in range(len(rows) + 1)]
    for index in range(len(rows) - 1, -1, -1):
        suffix[index] = suffix[index + 1].copy()
        for requirement_index, (field, value, _amount) in enumerate(requirements):
            suffix[index][requirement_index] += str(rows[index].get(field) or "") == value

    def search(index, picked, counts):
        if len(picked) == count:
            return (
                picked
                if all(
                    counts[j] >= need
                    for j, (_field, _value, need) in enumerate(requirements)
                )
                else None
            )
        if len(rows) - index < count - len(picked):
            return None
        if any(
            counts[j] + suffix[index][j] < need
            for j, (_field, _value, need) in enumerate(requirements)
        ):
            return None
        row = rows[index]
        next_counts = counts.copy()
        for j, (field, value, _need) in enumerate(requirements):
            next_counts[j] += str(row.get(field) or "") == value
        result = search(index + 1, picked + [row], next_counts)
        return result if result is not None else search(index + 1, picked, counts)

    result = search(0, [], [0] * len(requirements))
    if result is None:
        raise ValueError("無法同時滿足 topic、difficulty 與 cognitive quota")
    return result


def register_question_bank(base):
    app = base.app
    if app.extensions.get("teacher_question_bank_68_registered"):
        return app

    @app.post("/api/question-bank/drafts")
    def create_draft():
        denied = permitted(base)
        if denied:
            return denied
        try:
            payload = bank_service.create_draft(request.get_json(silent=True) or {})
        except ApiError as exc:
            return _error(exc)
        return jsonify(payload), 201

    @app.get("/api/question-bank")
    def list_bank():
        denied = (
            base.require_any_permission("question.manage", "audit.read")
            if hasattr(base, "require_any_permission")
            else base.require_admin()
        )
        if denied:
            return denied
        items = bank_service.list_questions(
            category_id=str(request.args.get("quizCategoryId") or "").strip(),
            status=str(request.args.get("status") or "").strip(),
        )
        return jsonify({"items": items})

    @app.patch("/api/question-bank/<question_id>")
    def update_bank_question(question_id):
        denied = permitted(base)
        if denied:
            return denied
        try:
            payload = bank_service.update_question(
                question_id,
                request.get_json(silent=True) or {},
            )
        except ApiError as exc:
            return _error(exc)
        return jsonify(payload)

    @app.delete("/api/question-bank/<question_id>")
    def delete_bank_question(question_id):
        denied = permitted(base)
        if denied:
            return denied
        return jsonify(bank_service.delete_question(question_id))

    @app.post("/api/question-bank/<question_id>/review")
    def review(question_id):
        denied = permitted(base, "question.review")
        if denied:
            return denied
        body = request.get_json(silent=True) or {}
        user = base._current_user() or {}
        try:
            payload = bank_service.review_question(
                question_id,
                decision=str(body.get("decision") or ""),
                username=str(user.get("username") or ""),
            )
        except ApiError as exc:
            return _error(exc)
        return jsonify(payload)

    # Blueprint persistence/selection remains a bounded legacy owner for the
    # next convergence slice.  Do not duplicate this logic in assessments yet.
    @app.post("/api/exam-blueprints")
    def blueprint():
        denied = permitted(base, "exam.manage")
        if denied:
            return denied
        body = request.get_json(silent=True) or {}
        count = max(1, min(500, int(body.get("questionCount", 0) or 0)))
        quotas = body.get("quotas") or {}
        if not isinstance(quotas, dict):
            return jsonify({"error": "quotas 格式錯誤"}), 400
        conn, kind = base._db_conn()
        ph = "%s" if kind == "postgres" else "?"
        blueprint_id = str(uuid.uuid4())
        try:
            conn.execute(
                f"INSERT INTO exam_blueprints(id,quiz_category_id,question_count,quotas,exclude_recent,created_by,created_at) VALUES({ph},{ph},{ph},{ph},{ph},{ph},{ph})",
                (
                    blueprint_id,
                    str(body.get("quizCategoryId") or ""),
                    count,
                    json.dumps(quotas),
                    max(0, int(body.get("excludeRecent", 0) or 0)),
                    (base._current_user() or {}).get("username", ""),
                    bank_service.now(),
                ),
            )
        finally:
            conn.close()
        return jsonify({
            "id": blueprint_id,
            "questionCount": count,
            "immutableSnapshotRequired": True,
        }), 201

    # Item analytics remains a bounded legacy owner for a later slice.
    @app.get("/api/questions/<question_id>/analytics")
    def analytics(question_id):
        denied = (
            base.require_any_permission("question.manage", "audit.read")
            if hasattr(base, "require_any_permission")
            else base.require_admin()
        )
        if denied:
            return denied
        conn, kind = base._db_conn()
        ph = "%s" if kind == "postgres" else "?"
        try:
            rows = conn.execute(
                f"SELECT selected_option,is_correct FROM question_attempt_analytics WHERE question_id={ph}",
                (question_id,),
            ).fetchall()
        finally:
            conn.close()
        attempt_count = len(rows)
        if attempt_count < 10:
            return jsonify({
                "attemptCount": attempt_count,
                "sufficientData": False,
                "message": "資料不足",
            })
        values = [dict(row) for row in rows]
        counts = dict(Counter(row["selected_option"] for row in values))
        conn, kind = base._db_conn()
        ph = "%s" if kind == "postgres" else "?"
        try:
            question = conn.execute(
                f"SELECT correct FROM quiz_questions WHERE id={ph}",
                (question_id,),
            ).fetchone()
        finally:
            conn.close()
        correct = str(dict(question).get("correct", "") if question else "")
        return jsonify({
            "attemptCount": attempt_count,
            "sufficientData": True,
            "correctRate": round(
                sum(bool(row["is_correct"]) for row in values) / attempt_count,
                3,
            ),
            "optionSelectionCounts": counts,
            "distractorDistribution": {
                key: value for key, value in counts.items() if str(key) != correct
            },
        })

    @app.post("/api/exam-blueprints/<blueprint_id>/publish")
    def publish_blueprint(blueprint_id):
        denied = permitted(base, "exam.publish")
        if denied:
            return denied
        conn, kind = base._db_conn()
        ph = "%s" if kind == "postgres" else "?"
        try:
            existing = conn.execute(
                f"SELECT id,questions,created_at FROM exam_blueprint_snapshots WHERE blueprint_id={ph}",
                (blueprint_id,),
            ).fetchone()
            if existing:
                row = dict(existing)
                return jsonify({
                    "id": row["id"],
                    "blueprintId": blueprint_id,
                    "questions": _decode(row["questions"], []),
                    "createdAt": row["created_at"],
                    "immutable": True,
                })
            bp = conn.execute(
                f"SELECT * FROM exam_blueprints WHERE id={ph}",
                (blueprint_id,),
            ).fetchone()
            if not bp:
                return jsonify({"error": "找不到 blueprint"}), 404
            bp = dict(bp)
            rows = [
                dict(row)
                for row in conn.execute(
                    f"SELECT * FROM quiz_questions WHERE quiz_category_id={ph} AND status IN ('reviewed','published') AND active={'TRUE' if kind == 'postgres' else '1'}",
                    (bp["quiz_category_id"],),
                ).fetchall()
            ]
            recent = set()
            if int(bp.get("exclude_recent") or 0) > 0:
                history = conn.execute(
                    f"SELECT questions FROM exam_blueprint_snapshots WHERE quiz_category_id={ph} ORDER BY created_at DESC LIMIT {int(bp['exclude_recent'])}",
                    (bp["quiz_category_id"],),
                ).fetchall()
                recent = {
                    str(question.get("id"))
                    for item in history
                    for question in _decode(dict(item).get("questions"), [])
                    if isinstance(question, dict)
                }
            try:
                chosen = _draw(
                    rows,
                    int(bp["question_count"]),
                    _decode(bp["quotas"], {}),
                    recent,
                )
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 409
            snapshot_id = str(uuid.uuid4())
            stamp = bank_service.now()
            packed = json.dumps(chosen, ensure_ascii=False)
            conn.execute(
                f"INSERT INTO exam_blueprint_snapshots(id,blueprint_id,quiz_category_id,questions,created_at) VALUES({ph},{ph},{ph},{ph},{ph})",
                (
                    snapshot_id,
                    blueprint_id,
                    bp["quiz_category_id"],
                    packed,
                    stamp,
                ),
            )
        finally:
            conn.close()
        return jsonify({
            "id": snapshot_id,
            "blueprintId": blueprint_id,
            "questionCount": len(chosen),
            "immutable": True,
            "createdAt": stamp,
        }), 201

    app.extensions["teacher_question_bank_68_registered"] = True
    return app
