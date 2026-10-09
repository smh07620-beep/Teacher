"""Owner-group + audience visibility policy for learning materials and questions.

A content item always keeps one owning group. ``audience_scope`` controls who
may consume the item without transferring ownership:

- ``group_only``: owning group only (safe default)
- ``all_staff``: every authenticated staff/learner
- ``multi_group``: owning group plus explicit additional groups
- ``source_only``: AI/出題/製作用的原始來源；學員不可見，只有負責組別的教師與跨組管理者可用

Cross-group education/system managers may inspect every item for governance,
but ordinary teachers still manage only their own group.
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Mapping

from flask import g, jsonify, request

from teacher_app.assessments import repository as assessment_repository
from teacher_app.assessments import runtime_questions
from teacher_app.common import audit, db as common_db, scope
from teacher_app.common.auth import has_permission, has_role


AUDIENCE_SCOPES = {"group_only", "all_staff", "multi_group", "source_only"}
AUDIENCE_LABELS = {
    "group_only": "本組限定",
    "all_staff": "全科共用",
    "multi_group": "指定組別",
    "source_only": "僅供老師製作使用",
}


def _current_user(owner=None) -> Mapping[str, Any] | None:
    user = getattr(g, "teacher_user", None)
    if user is not None:
        return user
    resolver = getattr(owner, "_current_user", None)
    return resolver() if callable(resolver) else None


def _preferred_group(user: Mapping[str, Any] | None) -> str:
    if not user:
        return ""
    value = user.get("preferredGroup") or user.get("preferred_group") or user.get("group") or ""
    return str(value).strip() if str(value).strip() in scope.GROUPS else ""


def _cross_group_manager(user: Mapping[str, Any] | None) -> bool:
    return bool(
        user
        and (
            has_role(user, "system_admin")
            or has_role(user, "education_admin")
            or has_permission(user, "education.cross_group.manage")
        )
    )


def _normalize_audience_scope(value: Any) -> str:
    candidate = str(value or "group_only").strip().lower()
    return candidate if candidate in AUDIENCE_SCOPES else "group_only"


def _decode_groups(value: Any) -> list[str]:
    raw = value
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "[]")
        except (TypeError, ValueError):
            raw = [part.strip() for part in raw.split(",") if part.strip()]
    if not isinstance(raw, (list, tuple, set)):
        raw = []
    output: list[str] = []
    for item in raw:
        key = str(item or "").strip()
        if key in scope.GROUPS and key not in output:
            output.append(key)
    return output


def _normalize_groups(value: Any, owner_group: str, audience_scope: str) -> list[str]:
    if audience_scope != "multi_group":
        return []
    groups = _decode_groups(value)
    # Ownership itself always grants visibility, so do not duplicate it in the
    # additional-groups payload.
    return [group for group in groups if group != owner_group]


def _column_exists(conn, kind: str, table: str, column: str) -> bool:
    if kind == "postgres":
        return bool(
            conn.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema=current_schema() AND table_name=%s AND column_name=%s",
                (table, column),
            ).fetchone()
        )
    return any(str(row[1]) == column for row in conn.execute(f"PRAGMA table_info({table})").fetchall())


def _material_meta(ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    values = [str(value) for value in ids if str(value)]
    if not values:
        return {}
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        placeholders = ",".join([ph] * len(values))
        has_scope = _column_exists(conn, kind, "materials", "audience_scope")
        has_groups = _column_exists(conn, kind, "materials", "audience_groups")
        columns = ["id", "group_key"]
        if _column_exists(conn, kind, "materials", "course_id"):
            columns.append("course_id")
        if has_scope:
            columns.append("audience_scope")
        if has_groups:
            columns.append("audience_groups")
        rows = conn.execute(
            f"SELECT {','.join(columns)} FROM materials WHERE id IN ({placeholders})",
            tuple(values),
        ).fetchall()
    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        data = dict(row)
        item_id = str(data.get("id") or "")
        owner_group = scope.normalize_group(data.get("group_key"))
        audience_scope = _normalize_audience_scope(data.get("audience_scope"))
        output[item_id] = {
            "courseId": str(data.get("course_id") or ""),
            "ownerGroup": owner_group,
            "audienceScope": audience_scope,
            "audienceGroups": _normalize_groups(data.get("audience_groups"), owner_group, audience_scope),
        }
    return output


def _question_meta(ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    values = [str(value) for value in ids if str(value)]
    if not values:
        return {}
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        placeholders = ",".join([ph] * len(values))
        has_scope = _column_exists(conn, kind, "quiz_questions", "audience_scope")
        has_groups = _column_exists(conn, kind, "quiz_questions", "audience_groups")
        columns = ["q.id", "c.group_key AS owner_group", "c.course_id AS course_id"]
        if has_scope:
            columns.append("q.audience_scope")
        if has_groups:
            columns.append("q.audience_groups")
        rows = conn.execute(
            "SELECT " + ",".join(columns) + " FROM quiz_questions q "
            "JOIN quiz_categories c ON c.id=q.quiz_category_id "
            f"WHERE q.id IN ({placeholders})",
            tuple(values),
        ).fetchall()
    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        data = dict(row)
        item_id = str(data.get("id") or "")
        owner_group = scope.normalize_group(data.get("owner_group"))
        audience_scope = _normalize_audience_scope(data.get("audience_scope"))
        output[item_id] = {
            "courseId": str(data.get("course_id") or ""),
            "ownerGroup": owner_group,
            "audienceScope": audience_scope,
            "audienceGroups": _normalize_groups(data.get("audience_groups"), owner_group, audience_scope),
        }
    return output


def can_author_with_source(user: Mapping[str, Any] | None, owner_group: str) -> bool:
    """``source_only`` 教材只給負責組別的教師／跨組管理者（不含學員）。"""
    if not user:
        return False
    if _cross_group_manager(user):
        return True
    authoring = any(has_permission(user, name) for name in ("material.manage", "question.manage", "course.manage"))
    return authoring and _preferred_group(user) == owner_group


def visible_to_user(user: Mapping[str, Any] | None, meta: Mapping[str, Any]) -> bool:
    if not user:
        return False
    if _normalize_audience_scope(meta.get("audienceScope")) == "source_only":
        return can_author_with_source(user, str(meta.get("ownerGroup") or ""))
    if _cross_group_manager(user):
        return True
    owner_group = str(meta.get("ownerGroup") or "")
    user_group = _preferred_group(user)
    if user_group and user_group == owner_group:
        return True
    audience_scope = _normalize_audience_scope(meta.get("audienceScope"))
    if audience_scope == "all_staff":
        return True
    if audience_scope == "multi_group" and user_group and user_group in _decode_groups(meta.get("audienceGroups")):
        return True
    course_id = str(meta.get("courseId") or "")
    if course_id:
        from teacher_app.learning import access as learning_access

        return course_id in learning_access.personal_course_grants(user)
    return False


def _can_manage(user: Mapping[str, Any] | None, permission: str, owner_group: str) -> bool:
    if not user or not has_permission(user, permission):
        return False
    return _cross_group_manager(user) or (_preferred_group(user) == owner_group)


def _write_audience(table: str, item_id: str, audience_scope: str, groups: list[str]) -> None:
    with common_db.transaction() as (conn, kind):
        if not _column_exists(conn, kind, table, "audience_scope"):
            raise RuntimeError("內容可見範圍 migration 尚未套用")
        ph = common_db.placeholder(kind)
        groups_json = json.dumps(groups, ensure_ascii=False, separators=(",", ":"))
        groups_value = f"{ph}::jsonb" if kind == "postgres" else ph
        conn.execute(
            f"UPDATE {table} SET audience_scope={ph},audience_groups={groups_value} WHERE id={ph}",
            (audience_scope, groups_json, item_id),
        )


def _update_payload(owner_group: str) -> tuple[str, list[str]]:
    body = request.get_json(silent=True) or {}
    audience_scope = _normalize_audience_scope(body.get("audienceScope"))
    groups = _normalize_groups(body.get("audienceGroups"), owner_group, audience_scope)
    if audience_scope == "multi_group" and not groups:
        raise ValueError("指定組別至少要選擇一個其他組別。")
    return audience_scope, groups


def _enrich_item(item: Mapping[str, Any], meta: Mapping[str, Any]) -> dict[str, Any]:
    output = dict(item)
    output.update({
        "ownerGroup": str(meta.get("ownerGroup") or output.get("group") or ""),
        "audienceScope": _normalize_audience_scope(meta.get("audienceScope")),
        "audienceGroups": _decode_groups(meta.get("audienceGroups")),
        "audienceLabel": AUDIENCE_LABELS[_normalize_audience_scope(meta.get("audienceScope"))],
    })
    return output


def register_content_audience(owner):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_content_audience_registered"):
        return app

    @app.patch("/api/content-audience/materials/<material_id>")
    def update_material_audience(material_id):
        user = _current_user(owner)
        meta = _material_meta([material_id]).get(str(material_id))
        if not meta:
            return jsonify({"error": "找不到教材。"}), 404
        if not _can_manage(user, "material.manage", meta["ownerGroup"]):
            return jsonify({"error": "權限不足：只能調整自己負責組別的教材可見範圍。"}), 403
        try:
            audience_scope, groups = _update_payload(meta["ownerGroup"])
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        before = dict(meta)
        _write_audience("materials", str(material_id), audience_scope, groups)
        after = {**meta, "audienceScope": audience_scope, "audienceGroups": groups}
        audit.record_event(
            actor=user or {},
            action="material.audience.update",
            target_type="material",
            target_id=str(material_id),
            group=meta["ownerGroup"],
            before=before,
            after=after,
        )
        return jsonify({"ok": True, **after, "audienceLabel": AUDIENCE_LABELS[audience_scope]})

    @app.patch("/api/content-audience/questions/<question_id>")
    def update_question_audience(question_id):
        user = _current_user(owner)
        meta = _question_meta([question_id]).get(str(question_id))
        if not meta:
            return jsonify({"error": "找不到題目。"}), 404
        if not _can_manage(user, "question.manage", meta["ownerGroup"]):
            return jsonify({"error": "權限不足：只能調整自己負責組別的題目可見範圍。"}), 403
        try:
            audience_scope, groups = _update_payload(meta["ownerGroup"])
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if audience_scope == "source_only":
            return jsonify({"error": "題目不支援「僅供老師製作使用」。"}), 400
        before = dict(meta)
        _write_audience("quiz_questions", str(question_id), audience_scope, groups)
        after = {**meta, "audienceScope": audience_scope, "audienceGroups": groups}
        audit.record_event(
            actor=user or {},
            action="question.audience.update",
            target_type="quiz_question",
            target_id=str(question_id),
            group=meta["ownerGroup"],
            before=before,
            after=after,
        )
        return jsonify({"ok": True, **after, "audienceLabel": AUDIENCE_LABELS[audience_scope]})

    @app.get("/api/content-audience/questions/shared")
    def list_shared_questions():
        user = _current_user(owner)
        if not user or not has_permission(user, "question.manage"):
            return jsonify({"error": "權限不足。"}), 403
        target_group = str(request.args.get("targetGroup") or _preferred_group(user) or "").strip()
        if target_group not in scope.GROUPS:
            return jsonify({"error": "請指定有效的目標組別。"}), 400
        if not (_cross_group_manager(user) or _preferred_group(user) == target_group):
            return jsonify({"error": "權限不足：無法管理此目標組別。"}), 403
        with common_db.read_connection() as (conn, kind):
            if not _column_exists(conn, kind, "quiz_questions", "audience_scope"):
                return jsonify([])
            rows = conn.execute(
                "SELECT q.*,c.group_key AS owner_group,c.title AS owner_category_title "
                "FROM quiz_questions q JOIN quiz_categories c ON c.id=q.quiz_category_id "
                "WHERE q.active=" + ("TRUE" if kind == "postgres" else "1") + " "
                "AND q.audience_scope IN ('all_staff','multi_group') "
                "ORDER BY c.group_key,q.sort_order,q.id"
            ).fetchall()
        output = []
        for row in rows:
            raw = dict(row)
            owner_group = scope.normalize_group(raw.pop("owner_group", scope.DEFAULT_GROUP))
            owner_title = str(raw.pop("owner_category_title", "") or "")
            audience_scope = _normalize_audience_scope(raw.get("audience_scope"))
            groups = _normalize_groups(raw.get("audience_groups"), owner_group, audience_scope)
            meta = {"ownerGroup": owner_group, "audienceScope": audience_scope, "audienceGroups": groups}
            if owner_group == target_group or visible_to_user({**dict(user), "preferredGroup": target_group}, meta):
                item = assessment_repository.question_row_to_dict(raw)
                item = _enrich_item(item, meta)
                item["ownerCategoryTitle"] = owner_title
                output.append(item)
        return jsonify(output[:300])

    @app.post("/api/content-audience/questions/<question_id>/copy")
    def copy_shared_question(question_id):
        user = _current_user(owner)
        if not user or not has_permission(user, "question.manage"):
            return jsonify({"error": "權限不足。"}), 403
        body = request.get_json(silent=True) or {}
        target_category_id = str(body.get("targetCategoryId") or "").strip()
        target_category = assessment_repository.get_category_full(target_category_id)
        if not target_category:
            return jsonify({"error": "找不到目標考卷／題目頁籤。"}), 404
        target_group = str(target_category.get("group") or "")
        if not _can_manage(user, "question.manage", target_group):
            return jsonify({"error": "權限不足：無法把題目加入此組考卷。"}), 403
        source_question = assessment_repository.get_question(str(question_id))
        source_meta = _question_meta([question_id]).get(str(question_id))
        if not source_question or not source_meta:
            return jsonify({"error": "找不到來源題目。"}), 404
        target_viewer = {**dict(user), "preferredGroup": target_group}
        if source_meta["ownerGroup"] != target_group and not visible_to_user(target_viewer, source_meta):
            return jsonify({"error": "此題目未分享給目標組別。"}), 403
        payload = {
            "quizCategoryId": target_category_id,
            "question": source_question.get("question", ""),
            "questionType": source_question.get("questionType", "choice"),
            "difficulty": source_question.get("difficulty", "standard"),
            "imageUrl": source_question.get("imageUrl", ""),
            "options": source_question.get("options", []),
            "correct": source_question.get("correct", 0),
            "answerConfig": source_question.get("answerConfig", {}),
            "tag": source_question.get("tag", ""),
            "explanation": source_question.get("explanation", ""),
            "active": True,
        }
        copied = runtime_questions.create_question(
            payload,
            allow_hosts=app.config.get("DIRECT_MEDIA_ALLOWLIST", []),
        )
        copied_id = str(copied.get("id") or "")
        if copied_id:
            _write_audience("quiz_questions", copied_id, "group_only", [])
        audit.record_event(
            actor=user or {},
            action="question.shared.copy",
            target_type="quiz_question",
            target_id=copied_id,
            group=target_group,
            detail={"sourceQuestionId": str(question_id), "sourceOwnerGroup": source_meta["ownerGroup"]},
        )
        return jsonify({"ok": True, "question": copied, "sourceQuestionId": str(question_id)}), 201

    @app.after_request
    def apply_content_audience(response):
        try:
            if request.method != "GET" or response.status_code != 200 or not response.is_json:
                return response
            path = request.path
            if path not in {
                "/api/slides",
                "/api/slides/admin",
                "/api/quiz-questions",
                "/api/quiz-questions/random",
                "/api/quiz-questions/admin",
            }:
                return response
            payload = response.get_json(silent=True)
            if not isinstance(payload, list):
                return response
            user = _current_user(owner)
            if path.startswith("/api/slides"):
                ids = [str(item.get("id") or "") for item in payload if isinstance(item, dict) and not item.get("isBuiltin")]
                meta_map = _material_meta(ids)
                output = []
                user_group = _preferred_group(user)
                for item in payload:
                    if not isinstance(item, dict):
                        continue
                    item_id = str(item.get("id") or "")
                    meta = meta_map.get(item_id) or {
                        "ownerGroup": scope.normalize_group(item.get("group")),
                        "audienceScope": "group_only",
                        "audienceGroups": [],
                    }
                    enriched = _enrich_item(item, meta)
                    if path == "/api/slides/admin":
                        if _cross_group_manager(user) or meta["ownerGroup"] == user_group:
                            output.append(enriched)
                        continue
                    if not visible_to_user(user, meta):
                        continue
                    # Existing learner UI groups cards by ``group``. Shared
                    # content is presented in the learner's own group while
                    # ownerGroup remains immutable for governance/admin views.
                    if user_group and meta["ownerGroup"] != user_group:
                        enriched["sharedFromGroup"] = meta["ownerGroup"]
                        enriched["group"] = user_group
                        # Cross-owner exam links must not silently jump into a
                        # different group's assessment category.
                        enriched["category"] = ""
                    output.append(enriched)
            else:
                ids = [str(item.get("id") or "") for item in payload if isinstance(item, dict)]
                meta_map = _question_meta(ids)
                output = []
                for item in payload:
                    if not isinstance(item, dict):
                        continue
                    item_id = str(item.get("id") or "")
                    meta = meta_map.get(item_id)
                    if not meta:
                        output.append(item)
                        continue
                    enriched = _enrich_item(item, meta)
                    if path == "/api/quiz-questions/admin" or visible_to_user(user, meta):
                        output.append(enriched)
            response.set_data(json.dumps(output, ensure_ascii=False, separators=(",", ":")))
            response.headers["Content-Type"] = "application/json; charset=utf-8"
        except Exception:
            app.logger.exception("content audience projection failed path=%s", request.path)
        return response

    app.extensions["teacher_content_audience_registered"] = True
    return app


__all__ = [
    "AUDIENCE_LABELS",
    "AUDIENCE_SCOPES",
    "register_content_audience",
    "visible_to_user",
]
