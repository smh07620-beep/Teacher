"""Teacher HTTP routes for AI-assisted lecture scripts."""
from __future__ import annotations

import datetime as dt
import os

from flask import g, jsonify, request

from teacher_app.common import audit, scope_filter
from teacher_app.materials import media_script_jobs, media_script_repository
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


def _public_script(script: dict) -> dict:
    return {
        key: script.get(key)
        for key in (
            "id", "materialId", "group", "area", "draftType", "title", "body", "status", "sourceJobId",
            "sourceChunks", "provider", "model", "fallbackUsed", "publicationMaterialId",
            "createdBy", "updatedBy", "approvedBy", "createdAt", "updatedAt", "approvedAt",
        )
    }


def register_media_script_routes(owner):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_media_script_routes_registered"):
        return app

    @app.post("/api/media-scripts/generate")
    def media_script_generate():
        user = _actor(owner)
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        body = request.get_json(silent=True) or {}
        body["outputType"] = "script"
        material_id = str(body.get("materialId") or "").strip()
        material = material_repository.get_material(material_id) if material_id else None
        # Media authoring is a pre-publication workflow. A teacher may prepare
        # narration from a draft material as long as normal material.manage
        # group scope allows it. Publication remains a separate explicit step.
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
                return jsonify({"error": "找不到其中一份講稿來源資料。"}), 404
            if (str(reference.get("group") or "") != str(material.get("group") or "")
                    or str(reference.get("area") or "") != str(material.get("area") or "")):
                return jsonify({"error": "講稿來源資料必須位於相同訓練區與組別。"}), 409
            denied = _scope(owner, str(reference.get("group") or ""))
            if denied:
                return denied
            reference_ids.append(reference_id)
        if len(reference_ids) > 9:
            return jsonify({"error": "一次最多可使用 10 份講稿來源資料。"}), 400
        body["referenceMaterialIds"] = reference_ids
        readiness_error = _ai_worker_online_error(required_queue="media_scripts")
        if readiness_error:
            return readiness_error
        # 同一份教材已有講稿工作在跑時不重複送出（省免費額度，也避免手滑連按），接續顯示原進度。
        try:
            lock_minutes = max(1, min(240, int(os.environ.get("MEDIA_SCRIPT_JOB_LOCK_MINUTES", "20"))))
        except ValueError:
            lock_minutes = 20
        since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=lock_minutes)).isoformat()
        running = media_script_repository.active_for_material(material_id, since=since)
        if running:
            payload = dict(media_script_jobs.public_job(running))
            payload["alreadyRunning"] = True
            return jsonify(payload), 202
        try:
            job = media_script_jobs.enqueue(body, user)
        except media_script_jobs.MediaScriptLimitError as exc:
            return jsonify({"error": str(exc), "rateLimited": True}), 429
        except LookupError as exc:
            return jsonify({"error": str(exc)}), 404
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        audit.record_event(
            actor=user,
            action="media.script.generate",
            target_type="material",
            target_id=material_id,
            group=str(material.get("group") or ""),
            detail={"jobId": job.get("id", ""), "targetMinutes": (job.get("request") or {}).get("targetMinutes", 0), "referenceMaterialIds": reference_ids},
        )
        return jsonify(media_script_jobs.public_job(job)), 202

    @app.get("/api/media-scripts/jobs/<media_script_job_id>")
    def media_script_job(media_script_job_id):
        user = _actor(owner)
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        job = media_script_repository.get_job(str(media_script_job_id))
        if not job:
            return jsonify({"error": "找不到講稿工作"}), 404
        denied = _scope(owner, str(job.get("group") or ""))
        if denied:
            return denied
        return jsonify(media_script_jobs.public_job(job))

    @app.get("/api/media-scripts")
    def media_scripts_list():
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
        return jsonify([_public_script(item) for item in media_script_repository.list_scripts(material_id)])

    @app.post("/api/media-scripts")
    def media_script_save():
        user = _actor(owner)
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        body = request.get_json(silent=True) or {}
        job_id = str(body.get("jobId") or "").strip()
        job = media_script_repository.get_job(job_id) if job_id else None
        if not job or job.get("status") != "completed":
            return jsonify({"error": "請先完成 AI 講稿草稿產生。"}), 409
        denied = _scope(owner, str(job.get("group") or ""))
        if denied:
            return denied
        title = str(body.get("title") or (job.get("result") or {}).get("title") or "教學講稿").strip()[:255]
        script_body = str(body.get("body") or "").strip()
        if len(script_body) < 80:
            return jsonify({"error": "講稿內容過短，請確認後再儲存。"}), 400
        if len(script_body) > 40000:
            return jsonify({"error": "講稿內容過長，請縮短至 40,000 字以內。"}), 400
        result = job.get("result") or {}
        script = media_script_repository.create_script(
            material_id=str(job.get("materialId") or result.get("sourceMaterialId") or ""),
            group_key=str(job.get("group") or ""),
            training_area=str(job.get("area") or ""),
            title=title,
            body=script_body,
            source_job_id=job_id,
            source_chunks=list(result.get("sourceChunks") or []),
            actor_username=str(user.get("username") or ""),
            draft_type="script",
            provider=str(result.get("provider") or ""),
            model=str(result.get("model") or ""),
            fallback_used=bool(result.get("fallbackUsed")),
        )
        audit.record_event(
            actor=user,
            action="media.script.create",
            target_type="media_script",
            target_id=str(script.get("id") or ""),
            group=str(script.get("group") or ""),
            after={"materialId": script.get("materialId"), "title": script.get("title"), "status": script.get("status")},
        )
        return jsonify({"ok": True, "script": _public_script(script)}), 201

    @app.patch("/api/media-scripts/<script_id>")
    def media_script_update(script_id):
        user = _actor(owner)
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        current = media_script_repository.get_script(str(script_id))
        if not current or str(current.get("draftType") or "script") != "script":
            return jsonify({"error": "找不到講稿"}), 404
        denied = _scope(owner, str(current.get("group") or ""))
        if denied:
            return denied
        body = request.get_json(silent=True) or {}
        title = str(body.get("title", current.get("title") or "教學講稿")).strip()[:255]
        script_body = str(body.get("body", current.get("body") or "")).strip()
        requested_status = str(body.get("status") or current.get("status") or "draft").strip().lower()
        status = requested_status if requested_status in {"draft", "approved"} else "draft"
        if len(script_body) < 80:
            return jsonify({"error": "講稿內容過短，請確認後再儲存。"}), 400
        if len(script_body) > 40000:
            return jsonify({"error": "講稿內容過長，請縮短至 40,000 字以內。"}), 400
        updated = media_script_repository.update_script(
            str(script_id), title=title, body=script_body, status=status,
            actor_username=str(user.get("username") or ""),
        )
        audit.record_event(
            actor=user,
            action="media.script.approve" if status == "approved" else "media.script.update",
            target_type="media_script",
            target_id=str(script_id),
            group=str(current.get("group") or ""),
            before={"title": current.get("title"), "status": current.get("status")},
            after={"title": (updated or {}).get("title"), "status": (updated or {}).get("status")},
            detail={"teacherConfirmed": status == "approved"},
        )
        return jsonify({"ok": True, "script": _public_script(updated or {})})

    @app.delete("/api/media-scripts/<script_id>")
    def media_script_discard(script_id):
        """Let a teacher abandon an unsatisfactory AI draft instead of keeping it forever."""
        user = _actor(owner)
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        current = media_script_repository.get_script(str(script_id))
        if not current or str(current.get("draftType") or "script") != "script":
            return jsonify({"error": "找不到講稿"}), 404
        denied = _scope(owner, str(current.get("group") or ""))
        if denied:
            return denied
        if not media_script_repository.delete_script(str(script_id)):
            return jsonify({"error": "找不到講稿"}), 404
        audit.record_event(
            actor=user,
            action="media.script.discard",
            target_type="media_script",
            target_id=str(script_id),
            group=str(current.get("group") or ""),
            before={"title": current.get("title"), "status": current.get("status")},
        )
        return jsonify({"ok": True, "deleted": str(script_id)})

    app.extensions["teacher_media_script_routes_registered"] = True
    return app


__all__ = ["register_media_script_routes"]
