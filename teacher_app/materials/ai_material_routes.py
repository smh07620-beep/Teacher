"""Teacher HTTP routes for reviewed AI material drafts.

Generation reuses the existing dedicated AI Worker/media-script queue.  Drafts
remain invisible to learners until the teacher explicitly publishes an approved
text artifact through the canonical material upload pipeline.
"""
from __future__ import annotations

from flask import g, jsonify, request

from teacher_app.common import audit, scope_filter
from teacher_app.materials import media_script_jobs, media_script_repository, media_script_runtime
from teacher_app.materials import repository as material_repository
from teacher_app.materials.media_audio_routes import _ai_worker_online_error


def _actor(owner=None):
    user = getattr(g, "teacher_user", None)
    if user is not None:
        return user
    resolver = getattr(owner, "_current_user", None)
    return resolver() if callable(resolver) else None


def _scope(owner, group: str):
    _user, denied = scope_filter.scoped_groups(owner, "material.manage", {str(group or "").strip()})
    return denied


def _public_draft(draft: dict) -> dict:
    return {
        key: draft.get(key)
        for key in (
            "id", "materialId", "group", "area", "draftType", "title", "body", "status", "sourceJobId",
            "sourceChunks", "provider", "model", "fallbackUsed", "publicationMaterialId",
            "createdBy", "updatedBy", "approvedBy", "createdAt", "updatedAt", "approvedAt",
        )
    }


def _validated_text(body: dict, fallback_title: str, fallback_body: str) -> tuple[str, str]:
    title = str(body.get("title") or fallback_title or "AI 教材草稿").strip()[:255]
    content = str(body.get("body") if "body" in body else fallback_body or "").strip()
    if len(content) < 60:
        raise ValueError("教材草稿內容過短，請確認後再儲存。")
    if len(content) > 40000:
        raise ValueError("教材草稿內容過長，請縮短至 40,000 字以內。")
    return title, content


def register_ai_material_routes(owner):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_ai_material_routes_registered"):
        return app

    @app.post("/api/ai-material-drafts/generate")
    def ai_material_generate():
        user = _actor(owner)
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        body = request.get_json(silent=True) or {}
        material_id = str(body.get("materialId") or "").strip()
        material = material_repository.get_material(material_id) if material_id else None
        if not material:
            return jsonify({"error": "找不到指定教材。"}), 404
        denied = _scope(owner, str(material.get("group") or ""))
        if denied:
            return denied
        reference_ids = []
        for value in body.get("referenceMaterialIds") or []:
            reference_id = str(value or "").strip()[:120]
            if not reference_id or reference_id == material_id or reference_id in reference_ids:
                continue
            reference = material_repository.get_material(reference_id)
            if not reference:
                return jsonify({"error": "找不到其中一份原始資料。"}), 404
            if (str(reference.get("group") or "") != str(material.get("group") or "")
                    or str(reference.get("area") or "") != str(material.get("area") or "")):
                return jsonify({"error": "原始資料必須位於相同訓練區與組別。"}), 409
            denied = _scope(owner, str(reference.get("group") or ""))
            if denied:
                return denied
            reference_ids.append(reference_id)
        if len(reference_ids) > 9:
            return jsonify({"error": "一次最多可使用 10 份原始資料。"}), 400
        body["referenceMaterialIds"] = reference_ids
        readiness_error = _ai_worker_online_error(required_queue="media_scripts")
        if readiness_error:
            return readiness_error
        try:
            output_type = media_script_runtime.normalize_output_type(body.get("outputType") or "summary")
            body["outputType"] = output_type
            job = media_script_jobs.enqueue(body, user)
        except media_script_jobs.MediaScriptLimitError as exc:
            return jsonify({"error": str(exc), "rateLimited": True}), 429
        except LookupError as exc:
            return jsonify({"error": str(exc)}), 404
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        audit.record_event(
            actor=user,
            action="ai.material.generate",
            target_type="material",
            target_id=material_id,
            group=str(material.get("group") or ""),
            detail={"jobId": job.get("id", ""), "draftType": output_type, "referenceMaterialIds": reference_ids},
        )
        return jsonify(media_script_jobs.public_job(job)), 202

    @app.get("/api/ai-material-drafts/jobs/<job_id>")
    def ai_material_job(job_id):
        user = _actor(owner)
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        job = media_script_repository.get_job(str(job_id))
        if not job:
            return jsonify({"error": "找不到 AI 教材工作"}), 404
        denied = _scope(owner, str(job.get("group") or ""))
        if denied:
            return denied
        return jsonify(media_script_jobs.public_job(job))

    @app.get("/api/ai-material-drafts")
    def ai_material_list():
        user = _actor(owner)
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        material_id = str(request.args.get("materialId") or "").strip()
        material = material_repository.get_material(material_id) if material_id else None
        if not material:
            return jsonify([] if not material_id else {"error": "找不到教材"}), 200 if not material_id else 404
        denied = _scope(owner, str(material.get("group") or ""))
        if denied:
            return denied
        return jsonify([_public_draft(item) for item in media_script_repository.list_drafts(material_id)])

    @app.post("/api/ai-material-drafts")
    def ai_material_save():
        user = _actor(owner)
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        body = request.get_json(silent=True) or {}
        job_id = str(body.get("jobId") or "").strip()
        job = media_script_repository.get_job(job_id) if job_id else None
        if not job or job.get("status") != "completed":
            return jsonify({"error": "請先完成 AI 教材草稿產生。"}), 409
        denied = _scope(owner, str(job.get("group") or ""))
        if denied:
            return denied
        result = job.get("result") or {}
        try:
            draft_type = media_script_runtime.normalize_output_type(result.get("outputType") or (job.get("request") or {}).get("outputType") or "summary")
            title, content = _validated_text(body, str(result.get("title") or ""), str(result.get("body") or ""))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        draft = media_script_repository.create_script(
            material_id=str(job.get("materialId") or result.get("sourceMaterialId") or ""),
            group_key=str(job.get("group") or ""),
            training_area=str(job.get("area") or ""),
            title=title,
            body=content,
            source_job_id=job_id,
            source_chunks=list(result.get("sourceChunks") or []),
            actor_username=str(user.get("username") or ""),
            draft_type=draft_type,
            provider=str(result.get("provider") or ""),
            model=str(result.get("model") or ""),
            fallback_used=bool(result.get("fallbackUsed")),
        )
        audit.record_event(
            actor=user,
            action="ai.material.draft.create",
            target_type="ai_material_draft",
            target_id=str(draft.get("id") or ""),
            group=str(draft.get("group") or ""),
            after={"materialId": draft.get("materialId"), "draftType": draft.get("draftType"), "status": draft.get("status")},
        )
        return jsonify({"ok": True, "draft": _public_draft(draft)}), 201

    @app.delete("/api/ai-material-drafts/<draft_id>")
    def ai_material_discard(draft_id):
        """Discard an unsatisfactory AI outline/draft that was never published."""
        user = _actor(owner)
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        current = media_script_repository.get_script(str(draft_id))
        if not current:
            return jsonify({"error": "找不到 AI 教材草稿"}), 404
        denied = _scope(owner, str(current.get("group") or ""))
        if denied:
            return denied
        if str(current.get("publicationMaterialId") or "").strip():
            return jsonify({"error": "這份草稿已發布成教材，不能直接刪除；請由教材管理處理。"}), 409
        if not media_script_repository.delete_script(str(draft_id)):
            return jsonify({"error": "找不到 AI 教材草稿"}), 404
        audit.record_event(
            actor=user,
            action="ai.material.draft.discard",
            target_type="ai_material_draft",
            target_id=str(draft_id),
            group=str(current.get("group") or ""),
            before={"title": current.get("title"), "draftType": current.get("draftType"), "status": current.get("status")},
        )
        return jsonify({"ok": True, "deleted": str(draft_id)})

    @app.patch("/api/ai-material-drafts/<draft_id>")
    def ai_material_update(draft_id):
        user = _actor(owner)
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        current = media_script_repository.get_script(str(draft_id))
        if not current:
            return jsonify({"error": "找不到 AI 教材草稿"}), 404
        denied = _scope(owner, str(current.get("group") or ""))
        if denied:
            return denied
        body = request.get_json(silent=True) or {}
        try:
            title, content = _validated_text(body, str(current.get("title") or ""), str(current.get("body") or ""))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        requested_status = str(body.get("status") or current.get("status") or "draft").strip().lower()
        status = requested_status if requested_status in {"draft", "approved"} else "draft"
        publication_id = None
        if "publicationMaterialId" in body:
            publication_id = str(body.get("publicationMaterialId") or "").strip()[:120]
            if publication_id:
                if str(current.get("status") or "") != "approved" and status != "approved":
                    return jsonify({"error": "AI 教材草稿必須先由教師核准，才能連結正式教材。"}), 409
                published = material_repository.get_material(publication_id)
                if not published:
                    return jsonify({"error": "找不到要連結的正式教材。"}), 404
                denied = _scope(owner, str(published.get("group") or ""))
                if denied:
                    return denied
                if str(published.get("group") or "") != str(current.get("group") or "") or str(published.get("area") or "") != str(current.get("area") or ""):
                    return jsonify({"error": "正式教材範圍與 AI 草稿來源範圍不一致。"}), 409
        updated = media_script_repository.update_script(
            str(draft_id),
            title=title,
            body=content,
            status=status,
            actor_username=str(user.get("username") or ""),
            publication_material_id=publication_id,
        )
        action = "ai.material.approve" if status == "approved" else "ai.material.update"
        if publication_id:
            action = "ai.material.publish_link"
        audit.record_event(
            actor=user,
            action=action,
            target_type="ai_material_draft",
            target_id=str(draft_id),
            group=str(current.get("group") or ""),
            before={"title": current.get("title"), "status": current.get("status"), "publicationMaterialId": current.get("publicationMaterialId")},
            after={"title": (updated or {}).get("title"), "status": (updated or {}).get("status"), "publicationMaterialId": (updated or {}).get("publicationMaterialId")},
            detail={"teacherConfirmed": status == "approved"},
        )
        return jsonify({"ok": True, "draft": _public_draft(updated or {})})

    app.extensions["teacher_ai_material_routes_registered"] = True
    return app


__all__ = ["register_ai_material_routes"]
