"""Teacher review APIs for the Phase 6 AI presentation-video pipeline."""
from __future__ import annotations

import datetime as dt

from flask import Response, abort, g, jsonify, redirect, request, send_file

from teacher_app.common import audit, scope_filter
from teacher_app.common.auth import has_role
from teacher_app.materials import ai_presentation_repository as presentation_repository
from teacher_app.materials import ai_video_jobs, ai_video_quality as quality, ai_video_renderer as renderer, ai_video_repository as repository
from teacher_app.materials import derivative_repository
from teacher_app.materials import repository as material_repository
from teacher_app.materials.ai_video_storage import VideoStorage
from teacher_app.materials.media_audio_routes import _ai_worker_online_error, _ai_worker_status

_TEACHER_ROLES = {"clinical_teacher", "group_leader"}
_OPERATE_ROLES = _TEACHER_ROLES | {"education_admin", "system_admin"}
_SHARED_BACKENDS = {"r2", "oci", "gdrive", "mega"}


def _actor(owner=None):
    user = getattr(g, "teacher_user", None)
    if user is not None:
        return user
    resolver = getattr(owner, "_current_user", None)
    return resolver() if callable(resolver) else None


def _scope(owner, group: str):
    _user, denied = scope_filter.scoped_groups(owner, "material.manage", {str(group or "").strip()})
    return denied


def _video_allowed(user, permission: str) -> bool:
    roles = _TEACHER_ROLES if permission == "video.approve" else _OPERATE_ROLES
    return bool(user and any(has_role(user, role) for role in roles))


def _artifact_ready(item: dict) -> bool:
    return bool(
        item
        and str(item.get("artifactBackend") or "").lower() in _SHARED_BACKENDS
        and item.get("artifactStorageKey")
        and len(str(item.get("artifactSha256") or "")) == 64
        and int(item.get("artifactBytes") or 0) > 0
        and item.get("artifactMimeType") == repository.MP4_MIME
        and float(item.get("durationSeconds") or 0) > 0
    )


def _effective_quality(item: dict) -> dict:
    manifest = quality.sanitize_quality_manifest(item.get("qualityManifest") or {})
    ruleset = str(item.get("renderRulesetVersion") or "").strip()
    if not ruleset:
        manifest = quality.add_warning(
            manifest,
            "LEGACY_QUALITY_UNVERIFIED",
            detail="此影片建立於正式影片品質規則前；發布前需人工確認。",
        )
    elif ruleset != quality.RULESET_VERSION:
        manifest = quality.add_warning(
            manifest,
            "RENDER_RULESET_OUTDATED",
            detail=f"此影片使用 {ruleset}；目前規則為 {quality.RULESET_VERSION}。發布前需重新預覽，或由目前規則重新產生。",
        )
    return manifest


def _public_video(item: dict) -> dict:
    keys = (
        "id",
        "videoFamilyId",
        "parentRevisionId",
        "revisionNumber",
        "presentationId",
        "presentationFamilyId",
        "presentationRevision",
        "presentationSha256",
        "group",
        "area",
        "title",
        "status",
        "artifactSha256",
        "artifactBytes",
        "artifactMimeType",
        "durationSeconds",
        "timeline",
        "ttsProvider",
        "ttsModel",
        "ttsVoice",
        "sourceJobId",
        "createdBy",
        "updatedBy",
        "approvedBy",
        "approvedAt",
        "publishedAt",
        "createdAt",
        "updatedAt",
        "renderRulesetVersion",
        "frameRenderer",
        "renderMetrics",
    )
    result = {key: item.get(key) for key in keys}
    result["qualityManifest"] = _effective_quality(item)
    result["previewUrl"] = f"/api/ai-videos/{item.get('id', '')}/preview" if _artifact_ready(item) else ""
    result["vttUrl"] = f"/api/ai-videos/{item.get('id', '')}.vtt" if item.get("vttText") else ""
    result["srtUrl"] = f"/api/ai-videos/{item.get('id', '')}.srt" if item.get("srtText") else ""
    return result


def _renderer_policy() -> dict:
    return {
        "order": list(renderer.RENDERER_ORDER),
        "resolvedOn": "local-ai-worker",
        "powerPoint": {
            "id": renderer.POWERPOINT,
            "requiresWorkingActivation": True,
            "boundedTimeout": True,
        },
        "libreOffice": {
            "id": renderer.LIBREOFFICE,
            "freeFallback": True,
            "headless": True,
        },
        "safeFallback": {
            "id": renderer.SAFE_FALLBACK,
            "alwaysAvailable": True,
            "requiresPublicationWarningAcknowledgement": True,
        },
    }


def register_ai_video_routes(owner):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_ai_video_routes_registered"):
        return app

    @app.get("/api/ai-videos/status")
    def video_status():
        user = _actor(owner)
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        if not _video_allowed(user, "video.create"):
            return jsonify({"error": "目前角色不可建立 AI 影片。"}), 403
        storage = VideoStorage().capability()
        worker = _ai_worker_status()
        ready = bool(
            storage.get("available")
            and worker.get("online")
            and "ai_videos" in set(worker.get("queues") or [])
            and worker.get("kokoroInstalled") is True
        )
        if not storage.get("available"):
            diagnostic = str(storage.get("reason") or "AI 影片共用儲存尚未就緒；請確認 R2／OCI／Google Drive／MEGA 設定。")
        elif not worker.get("online"):
            diagnostic = str(worker.get("diagnosticMessage") or "AI Worker 尚未在線。")
        elif "ai_videos" not in set(worker.get("queues") or []):
            diagnostic = "AI Worker 已在線，但尚未回報 ai_videos queue；請更新院內 Worker 後重啟。"
        elif worker.get("kokoroInstalled") is not True:
            diagnostic = str(worker.get("diagnosticMessage") or "Kokoro 尚未就緒。")
        else:
            diagnostic = "AI Worker、Kokoro 與影片共用儲存均已就緒。"
        return jsonify(
            {
                "storage": storage,
                "worker": worker,
                "ready": ready,
                "diagnostic": {"code": "ready" if ready else str(worker.get("diagnosticCode") or "video_not_ready"), "message": diagnostic},
                "workerRequired": True,
                "requiresApprovedPresentation": True,
                "qualityRulesetVersion": quality.RULESET_VERSION,
                "preferredFrameRenderer": renderer.POWERPOINT,
                "rendererPolicy": _renderer_policy(),
                "capabilities": {
                    name: _video_allowed(user, name)
                    for name in ("video.create", "video.approve", "video.publish")
                },
            }
        )

    @app.post("/api/ai-videos/generate")
    def video_generate():
        user = _actor(owner)
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        if not _video_allowed(user, "video.create"):
            return jsonify({"error": "目前角色不可建立 AI 影片。"}), 403
        worker = _ai_worker_status()
        readiness_error = _ai_worker_online_error(worker, required_queue="ai_videos")
        if readiness_error:
            return readiness_error
        if worker.get("kokoroInstalled") is not True:
            return jsonify({
                "error": str(worker.get("diagnosticMessage") or "Kokoro 尚未就緒，暫不建立影片工作。"),
                "kokoroUnavailable": True,
                "worker": worker,
            }), 503
        body = request.get_json(silent=True) or {}
        presentation = presentation_repository.get_presentation(str(body.get("presentationId") or ""))
        if not presentation:
            return jsonify({"error": "找不到 PowerPoint revision。"}), 404
        denied = _scope(owner, str(presentation.get("group") or ""))
        if denied:
            return denied
        if str(presentation.get("status") or "") not in {"approved", "published"}:
            return jsonify({"error": "AI 影片來源必須是已由授課教師核准的 PowerPoint revision。"}), 409
        if (presentation.get("qualityManifest") or {}).get("status") == "error":
            return jsonify({"error": "PowerPoint revision 仍有阻擋品質錯誤，不能產生正式教學影片。", "qualityBlocked": True}), 409
        if not presentation.get("artifactStorageKey") or len(str(presentation.get("artifactSha256") or "")) != 64:
            return jsonify({"error": "PowerPoint durable artifact metadata 不完整。"}), 409
        try:
            job = ai_video_jobs.enqueue(body, user, presentation)
        except ai_video_jobs.AiVideoLimitError as exc:
            return jsonify({"error": str(exc), "rateLimited": True}), 429
        except (ValueError, RuntimeError) as exc:
            return jsonify({"error": str(exc), "notConfigured": True}), 503
        audit.record_event(
            actor=user,
            action="video.generate",
            target_type="ai_presentation",
            target_id=str(presentation.get("id") or ""),
            group=str(presentation.get("group") or ""),
            detail={
                "jobId": job.get("id"),
                "presentationRevision": presentation.get("revisionNumber"),
                "renderedInWeb": False,
                "ruleset": quality.RULESET_VERSION,
                "rendererOrder": list(renderer.RENDERER_ORDER),
            },
        )
        return jsonify(ai_video_jobs.public_job(job)), 202

    @app.get("/api/ai-videos/jobs/<job_id>")
    def video_job(job_id):
        user = _actor(owner)
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        job = repository.get_job(str(job_id))
        if not job:
            return jsonify({"error": "找不到 AI 影片工作。"}), 404
        denied = _scope(owner, str(job.get("group") or ""))
        return denied if denied else jsonify(ai_video_jobs.public_job(job))

    @app.post("/api/ai-videos/jobs/<job_id>/retry")
    def video_retry_job(job_id):
        user = _actor(owner)
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        if not _video_allowed(user, "video.create"):
            return jsonify({"error": "目前角色不可重試 AI 影片工作。"}), 403
        job = repository.get_job(str(job_id))
        if not job:
            return jsonify({"error": "找不到 AI 影片工作。"}), 404
        denied = _scope(owner, str(job.get("group") or ""))
        if denied:
            return denied
        retried = ai_video_jobs.retry(job)
        if not retried:
            return jsonify({"error": "此工作不是可安全重試的失敗狀態，或已達重試上限。"}), 409
        audit.record_event(
            actor=user,
            action="video.retry",
            target_type="ai_video_job",
            target_id=str(job_id),
            group=str(job.get("group") or ""),
            detail={"attempts": job.get("attempts")},
        )
        return jsonify(ai_video_jobs.public_job(retried)), 202

    @app.get("/api/ai-presentations/<presentation_id>/videos")
    def presentation_videos(presentation_id):
        user = _actor(owner)
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        presentation = presentation_repository.get_presentation(str(presentation_id))
        if not presentation:
            return jsonify({"error": "找不到 PowerPoint revision。"}), 404
        denied = _scope(owner, str(presentation.get("group") or ""))
        return denied if denied else jsonify(
            {"videos": [_public_video(item) for item in repository.list_videos(str(presentation_id))]}
        )

    @app.get("/api/ai-videos/<video_id>/quality")
    def video_quality(video_id):
        user = _actor(owner)
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        video = repository.get_video(str(video_id))
        if not video:
            return jsonify({"error": "找不到 AI 影片。"}), 404
        denied = _scope(owner, str(video.get("group") or ""))
        if denied:
            return denied
        return jsonify(
            {
                "videoId": video_id,
                "quality": _effective_quality(video),
                "renderMetrics": video.get("renderMetrics") or {},
                "frameRenderer": video.get("frameRenderer") or "",
                "rendererPolicy": _renderer_policy(),
            }
        )

    @app.get("/api/ai-videos/<video_id>/preview")
    def video_preview(video_id):
        user = _actor(owner)
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        video = repository.get_video(str(video_id))
        if not video:
            abort(404)
        denied = _scope(owner, str(video.get("group") or ""))
        if denied:
            return denied
        if not _artifact_ready(video):
            return jsonify({"error": "AI 影片 artifact 尚未完成。"}), 409
        try:
            response = VideoStorage().browser_response(
                video,
                download_name=f"{video.get('title') or 'AI教學影片'}-r{video.get('revisionNumber') or 1}.mp4",
            )
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 503
        if isinstance(response, str):
            return redirect(response, code=302)
        return (
            send_file(response, mimetype=repository.MP4_MIME, as_attachment=False, download_name=response.name)
            if hasattr(response, "name")
            else response
        )

    def _caption(video_id: str, suffix: str):
        user = _actor(owner)
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        video = repository.get_video(str(video_id))
        if not video:
            abort(404)
        denied = _scope(owner, str(video.get("group") or ""))
        if denied:
            return denied
        text = str(video.get("vttText" if suffix == "vtt" else "srtText") or "")
        if not text:
            abort(404)
        return Response(text, mimetype="text/vtt" if suffix == "vtt" else "application/x-subrip")

    @app.get("/api/ai-videos/<video_id>.vtt")
    def video_vtt(video_id):
        return _caption(video_id, "vtt")

    @app.get("/api/ai-videos/<video_id>.srt")
    def video_srt(video_id):
        return _caption(video_id, "srt")

    @app.post("/api/ai-videos/<video_id>/approve")
    def video_approve(video_id):
        user = _actor(owner)
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        if not _video_allowed(user, "video.approve"):
            return jsonify({"error": "只有臨床教師或組長可核准 AI 影片。"}), 403
        video = repository.get_video(str(video_id))
        if not video:
            return jsonify({"error": "找不到 AI 影片。"}), 404
        denied = _scope(owner, str(video.get("group") or ""))
        if denied:
            return denied
        if not _artifact_ready(video):
            return jsonify({"error": "AI 影片 artifact durable metadata 不完整。"}), 409
        if _effective_quality(video).get("status") == "error":
            return jsonify({"error": "AI 影片有阻擋品質錯誤，不能核准。", "qualityBlocked": True}), 409
        try:
            updated = repository.set_status(
                str(video_id),
                status="approved",
                actor_username=str(user.get("username") or ""),
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 409
        audit.record_event(
            actor=user,
            action="video.approve",
            target_type="ai_presentation_video",
            target_id=str(video_id),
            group=str(video.get("group") or ""),
            after={
                "status": "approved",
                "artifactSha256": video.get("artifactSha256"),
                "qualityStatus": _effective_quality(video).get("status"),
                "frameRenderer": video.get("frameRenderer"),
            },
        )
        return jsonify({"ok": True, "video": _public_video(updated or {})})

    @app.post("/api/ai-videos/<video_id>/publish")
    def video_publish(video_id):
        user = _actor(owner)
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        if not _video_allowed(user, "video.publish"):
            return jsonify({"error": "目前角色不可發布 AI 影片。"}), 403
        video = repository.get_video(str(video_id))
        if not video:
            return jsonify({"error": "找不到 AI 影片。"}), 404
        denied = _scope(owner, str(video.get("group") or ""))
        if denied:
            return denied
        if str(video.get("status") or "") not in {"approved", "published"} or not _artifact_ready(video):
            return jsonify({"error": "AI 影片必須先由授課教師核准且具完整 durable artifact。"}), 409
        body = request.get_json(silent=True) or {}
        manifest = _effective_quality(video)
        if manifest.get("status") == "error":
            return jsonify({"error": "發布前品質檢查有阻擋錯誤。", "quality": manifest, "qualityBlocked": True}), 409
        warning_ack = None
        if manifest.get("status") == "warning":
            if body.get("acknowledgeWarnings") is not True:
                return jsonify(
                    {
                        "error": "此影片有品質警告；請確認預覽與警告後再發布。",
                        "quality": manifest,
                        "requiresWarningAcknowledgement": True,
                    }
                ), 409
            warning_ack = {
                "actor": str(user.get("username") or ""),
                "at": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
            audit.record_event(
                actor=user,
                action="video.quality-warning-acknowledge",
                target_type="ai_presentation_video",
                target_id=str(video_id),
                group=str(video.get("group") or ""),
                detail={
                    "ruleset": manifest.get("rulesetVersion"),
                    "warningCodes": [item.get("code") for item in manifest.get("warnings", [])],
                    "frameRenderer": video.get("frameRenderer"),
                },
            )
        presentation = presentation_repository.get_presentation(str(video.get("presentationId") or ""))
        if not presentation:
            return jsonify({"error": "找不到影片來源 PowerPoint revision，拒絕發布。"}), 409
        presentation_publication = presentation_repository.get_publication_for_presentation(
            str(presentation.get("id") or "")
        )
        material_id = str(
            (presentation_publication or {}).get("publicationMaterialId")
            or presentation.get("materialId")
            or ""
        )
        material = material_repository.get_material(material_id) if material_id else None
        if not material:
            return jsonify({"error": "找不到影片所屬 canonical 教材，拒絕發布。"}), 409
        denied = _scope(owner, str(material.get("group") or ""))
        if denied:
            return denied
        if material.get("group") != video.get("group") or material.get("area") != video.get("area"):
            return jsonify({"error": "影片與 canonical 教材範圍不一致，拒絕發布。"}), 409

        receipt_payload = {
            "videoId": video.get("id"),
            "videoRevision": video.get("revisionNumber"),
            "presentationId": video.get("presentationId"),
            "presentationRevision": video.get("presentationRevision"),
            "presentationSha256": video.get("presentationSha256"),
            "artifactBackend": video.get("artifactBackend"),
            "artifactStorageKey": video.get("artifactStorageKey"),
            "artifactSha256": video.get("artifactSha256"),
            "artifactBytes": video.get("artifactBytes"),
            "artifactMimeType": video.get("artifactMimeType"),
            "durationSeconds": video.get("durationSeconds"),
            "qualityStatus": manifest.get("status"),
            "qualityRulesetVersion": manifest.get("rulesetVersion"),
            "frameRenderer": video.get("frameRenderer"),
            "publicationMaterialId": material_id,
        }
        snapshot = {
            **receipt_payload,
            "timeline": list(video.get("timeline") or []),
            "rendererAttempts": list((video.get("renderMetrics") or {}).get("rendererAttempts") or []),
            "warningAcknowledgement": warning_ack or {},
        }
        receipt = repository.create_publication(
            video_id=str(video_id),
            actor_username=str(user.get("username") or ""),
            receipt=receipt_payload,
            snapshot=snapshot,
            video_family_id=str(video.get("videoFamilyId") or video.get("id") or ""),
            video_revision_number=int(video.get("revisionNumber") or 1),
        )
        try:
            derivative = derivative_repository.record_publication(
                material_id=material_id,
                derivative_type="video",
                derivative_id=str(video.get("id") or ""),
                source_presentation_id=str(presentation.get("id") or ""),
                source_presentation_revision=int(presentation.get("revisionNumber") or 1),
                artifact={
                    "backend": str(video.get("artifactBackend") or ""),
                    "key": str(video.get("artifactStorageKey") or ""),
                    "sha256": str(video.get("artifactSha256") or ""),
                    "byteSize": int(video.get("artifactBytes") or 0),
                    "mimeType": str(video.get("artifactMimeType") or ""),
                },
                receipt_key=str(receipt.get("receiptKey") or ""),
                provenance={
                    "sourceMaterialId": material_id,
                    "sourceMaterialVersion": int(
                        (presentation.get("provenance") or {}).get("sourceMaterialVersion")
                        or material.get("currentVersion")
                        or 1
                    ),
                    "presentationId": str(presentation.get("id") or ""),
                    "presentationRevision": int(presentation.get("revisionNumber") or 1),
                    "presentationSha256": str(presentation.get("artifactSha256") or ""),
                    "ttsProvider": str(video.get("ttsProvider") or ""),
                    "ttsModel": str(video.get("ttsModel") or ""),
                    "ttsVoice": str(video.get("ttsVoice") or ""),
                    "frameRenderer": str(video.get("frameRenderer") or ""),
                    "qualityStatus": str(manifest.get("status") or ""),
                    "qualityRulesetVersion": str(manifest.get("rulesetVersion") or ""),
                },
                published_by=str(user.get("username") or ""),
            )
        except (ValueError, RuntimeError) as exc:
            return jsonify({"error":str(exc)}), 409
        updated = repository.set_status(
            str(video_id),
            status="published",
            actor_username=str(user.get("username") or ""),
        )
        audit.record_event(
            actor=user,
            action="video.publish",
            target_type="ai_presentation_video",
            target_id=str(video_id),
            group=str(video.get("group") or ""),
            after={
                "status": "published",
                "receiptKey": receipt.get("receiptKey"),
                "qualityStatus": manifest.get("status"),
                "frameRenderer": video.get("frameRenderer"),
            },
        )
        return jsonify({
            "ok": True,
            "video": _public_video(updated or {}),
            "publicationReceipt": receipt,
            "materialDerivative": derivative,
        })

    app.extensions["teacher_ai_video_routes_registered"] = True
    return app


__all__ = [
    "register_ai_video_routes",
    "_artifact_ready",
    "_effective_quality",
    "_renderer_policy",
    "_video_allowed",
]
