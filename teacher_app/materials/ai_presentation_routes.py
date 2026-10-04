"""Teacher-facing APIs for reviewed AI PowerPoint authoring."""
from __future__ import annotations

import datetime as dt
import os
import json
import re
import tempfile
import uuid
import zipfile
from pathlib import Path

from flask import g, jsonify, request, send_file

from teacher_app.common import audit, scope, scope_filter
from teacher_app.common.auth import has_role
from teacher_app.materials import ai_presentation_jobs
from teacher_app.materials import ai_presentation_repository as repository
from teacher_app.materials import ai_presentation_runtime
from teacher_app.materials import ai_presentation_quality as quality
from teacher_app.materials.ai_presentation_storage import PPTX_MIME, PresentationStorage, safe_filename
from teacher_app.materials import media_script_repository
from teacher_app.materials import repository as material_repository

_TEACHER_APPROVAL_ROLES = {"clinical_teacher", "group_leader"}
_PUBLISH_ROLES = {"clinical_teacher", "group_leader", "education_admin", "system_admin"}
_PRESENTATION_CAPABILITIES = {
    "presentation.create": {"clinical_teacher", "group_leader", "education_admin", "system_admin"},
    "presentation.edit": {"clinical_teacher", "group_leader", "education_admin", "system_admin"},
    "presentation.approve": {"clinical_teacher", "group_leader"},
    "presentation.publish": {"clinical_teacher", "group_leader", "education_admin", "system_admin"},
}
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


def _presentation_allowed(user, permission: str) -> bool:
    return bool(user and any(has_role(user, role) for role in _PRESENTATION_CAPABILITIES.get(permission, set())))


def _capability(user, permission: str, message: str):
    return None if _presentation_allowed(user, permission) else (jsonify({"error": message}), 403)


def _teacher_approval(user):
    if _presentation_allowed(user, "presentation.approve") and any(has_role(user, role) for role in _TEACHER_APPROVAL_ROLES):
        return None
    return jsonify({"error": "只有臨床教師或組長可核准 AI PowerPoint。"}), 403


def _publisher(user):
    if _presentation_allowed(user, "presentation.publish") and any(has_role(user, role) for role in _PUBLISH_ROLES):
        return None
    return jsonify({"error": "目前角色不可發布 AI PowerPoint。"}), 403


def _public_template(item: dict) -> dict:
    keys = ("id","name","group","area","active","sha256","byteSize","mimeType","layoutProfile","createdBy","createdAt","updatedAt")
    return {key: item.get(key) for key in keys}


def _effective_quality(item: dict) -> dict:
    persisted = quality.sanitize_quality_manifest(item.get("qualityManifest") or {})
    if str(item.get("renderRulesetVersion") or "") == quality.RULESET_VERSION and int(persisted.get("slideCount") or 0) > 0:
        return persisted
    try:
        _prepared, manifest = quality.prepare_slides(
            ai_presentation_runtime.normalize_slides(list(item.get("slides") or [])),
            provenance_present=bool((item.get("provenance") or {}).get("sourceMaterialId") and (item.get("provenance") or {}).get("sourceDraftId")),
        )
        return manifest
    except ValueError:
        return quality.sanitize_quality_manifest({
            "rulesetVersion": quality.RULESET_VERSION,
            "errors": [{"code":"NO_RENDERABLE_SLIDES","detail":"沒有可產生的投影片。"}],
        })


def _render_observability(item: dict) -> dict:
    metrics = quality.sanitize_render_metrics(item.get("renderMetrics") or {})
    job_id = str(metrics.get("jobId") or "")
    job = repository.get_job(job_id) if job_id else None
    if job:
        metrics["attempts"] = int(job.get("attempts") or metrics.get("attempts") or 0)
        metrics["lastError"] = str(job.get("error") or metrics.get("lastError") or "")[:500]
        metrics["jobStatus"] = str(job.get("status") or "")
    else:
        metrics["jobStatus"] = ""
    return metrics


def _public_presentation(item: dict) -> dict:
    keys = (
        "id","presentationFamilyId","parentVersionId","revisionNumber","materialId","draftId","templateId",
        "group","area","title","status","slides","artifactSha256","artifactBytes","artifactMimeType",
        "provider","model","sourceJobId","createdBy","updatedBy","approvedBy","approvedAt","publishedAt",
        "createdAt","updatedAt","renderRulesetVersion",
    )
    payload = {key: item.get(key) for key in keys}
    manifest = _effective_quality(item)
    payload["artifactReady"] = _artifact_ready(item)
    payload["provenanceAvailable"] = bool(item.get("provenance", {}).get("sourceMaterialId"))
    payload["qualityManifest"] = manifest
    payload["qualityStatus"] = manifest.get("status")
    payload["renderMetrics"] = _render_observability(item)
    return payload


def _quality_snapshot(manifest: dict, *, warning_ack: dict | None = None) -> dict:
    safe = quality.sanitize_quality_manifest(manifest)
    payload = {
        "rulesetVersion": safe.get("rulesetVersion"),
        "status": safe.get("status"),
        "slideCount": safe.get("slideCount"),
        "warningCount": safe.get("warningCount"),
        "errorCount": safe.get("errorCount"),
        "warningCodes": [str(item.get("code") or "") for item in safe.get("warnings", [])],
        "errorCodes": [str(item.get("code") or "") for item in safe.get("errors", [])],
    }
    if warning_ack:
        payload["warningAcknowledgement"] = {
            "acknowledged": True,
            "actor": str(warning_ack.get("actor") or "")[:120],
            "at": str(warning_ack.get("at") or "")[:80],
        }
    return payload


def _publication_snapshot(item: dict, *, manifest: dict | None = None, warning_ack: dict | None = None) -> dict:
    """A public-safe immutable record of precisely what the release points at."""
    return {
        "presentationId": str(item.get("id") or ""), "presentationFamilyId": str(item.get("presentationFamilyId") or ""),
        "revisionNumber": int(item.get("revisionNumber") or 1), "title": str(item.get("title") or "")[:255],
        "artifact": {"backend": str(item.get("artifactBackend") or ""), "key": str(item.get("artifactStorageKey") or ""),
                     "sha256": str(item.get("artifactSha256") or ""), "byteSize": int(item.get("artifactBytes") or 0),
                     "mimeType": str(item.get("artifactMimeType") or "")},
        "templateId": str(item.get("templateId") or ""), "provenance": item.get("provenance") or {},
        "approvedBy": str(item.get("approvedBy") or ""), "approvedAt": str(item.get("approvedAt") or ""),
        "quality": _quality_snapshot(manifest or _effective_quality(item), warning_ack=warning_ack),
    }


def _validated_pptx_upload(upload, *, max_mb: int) -> Path:
    filename = str(getattr(upload, "filename", "") or "")
    if Path(filename).suffix.lower() != ".pptx":
        raise ValueError("只接受 .pptx 範本或教師修正版。")
    limit = max(1, min(50, int(max_mb))) * 1024 * 1024
    handle = tempfile.NamedTemporaryFile(prefix="teacher-ppt-upload-", suffix=".pptx", delete=False)
    path, size = Path(handle.name), 0
    try:
        with handle:
            while True:
                chunk = upload.stream.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    raise ValueError(f"PowerPoint 檔案不可超過 {max_mb} MB。")
                handle.write(chunk)
        if size < 1024:
            raise ValueError("PowerPoint 檔案為空白或不完整。")
        try:
            with zipfile.ZipFile(path) as archive:
                names = {name.lower() for name in archive.namelist()}
                if "[content_types].xml" not in names or not any(name.startswith("ppt/") for name in names):
                    raise ValueError("檔案不是有效的 PowerPoint Open XML。")
                if any("vbaproject.bin" in name or name.endswith(".vba") for name in names):
                    raise ValueError("禁止上傳含 VBA 巨集的 PowerPoint。")
                if archive.testzip():
                    raise ValueError("PowerPoint 壓縮內容已損壞。")
        except zipfile.BadZipFile as exc:
            raise ValueError("PowerPoint 檔案格式無效。") from exc
        return path
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _artifact(item: dict) -> dict:
    return {
        "backend": item.get("artifactBackend"), "key": item.get("artifactStorageKey"),
        "sha256": item.get("artifactSha256"), "byteSize": item.get("artifactBytes"),
        "mimeType": item.get("artifactMimeType"),
    }


def _local_artifact_enabled() -> bool:
    return str(os.environ.get("AI_PRESENTATION_ALLOW_LOCAL_STORAGE", "false")).strip().lower() in {"1","true","yes","on"}


def _artifact_ready(item: dict) -> bool:
    backend = str(item.get("artifactBackend") or "").lower()
    key = str(item.get("artifactStorageKey") or "").strip()
    digest = str(item.get("artifactSha256") or "").strip().lower()
    size = int(item.get("artifactBytes") or 0)
    mime = str(item.get("artifactMimeType") or "").strip()
    provider_ok = backend in _SHARED_BACKENDS or (backend == "local" and _local_artifact_enabled())
    return bool(provider_ok and key and re.fullmatch(r"[0-9a-f]{64}", digest) and size > 0 and mime == PPTX_MIME)


def _durable_material(material: dict) -> bool:
    return str(material.get("storageBackend") or "").lower() in _SHARED_BACKENDS and bool(str(material.get("storageKey") or "").strip())


def register_ai_presentation_routes(owner):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_ai_presentation_routes_registered"):
        return app

    @app.get("/api/ai-presentations/status")
    def presentation_status():
        user = _actor(owner)
        if not user:
            return jsonify({"error":"請先登入。","loginRequired":True}), 401
        storage = PresentationStorage().capability()
        return jsonify({
            "productPhase": "F5",
            "storage": storage,
            "workerRequired": True,
            "requiresApprovedSlideDraft": True,
            "teacherApprovalRoles": sorted(_TEACHER_APPROVAL_ROLES),
            "qualityRulesetVersion": quality.RULESET_VERSION,
            "workflow": {
                "source": "approved-slides-draft",
                "template": "group-area-template",
                "render": "dedicated-ai-worker",
                "artifact": "shared-durable-pptx",
                "review": "immutable-revision",
                "teacherApproval": True,
                "videoHandoff": True,
                "ready": bool(storage.get("available")),
            },
            "capabilities": {name: _presentation_allowed(user, name) for name in _PRESENTATION_CAPABILITIES},
        })

    @app.get("/api/ai-presentation-templates")
    def template_list():
        user = _actor(owner)
        if not user:
            return jsonify({"error":"請先登入。","loginRequired":True}), 401
        group = str(request.args.get("group") or user.get("preferredGroup") or user.get("preferred_group") or "").strip()
        area = str(request.args.get("area") or "").strip()
        if group:
            denied = _scope(owner, group)
            if denied: return denied
        if area:
            try: area = scope.validate_area(area, default=None)
            except ValueError as exc: return jsonify({"error":str(exc)}), 400
        return jsonify([_public_template(item) for item in repository.list_templates(group_key=group, training_area=area)])

    @app.post("/api/ai-presentation-templates")
    def template_upload():
        user = _actor(owner)
        if not user:
            return jsonify({"error":"請先登入。","loginRequired":True}), 401
        group, area = str(request.form.get("group") or "").strip(), str(request.form.get("area") or "").strip()
        try: group, area = scope.validate_group(group, default=None), scope.validate_area(area, default=None)
        except ValueError as exc: return jsonify({"error":str(exc)}), 400
        denied = _scope(owner, group)
        if denied: return denied
        upload = request.files.get("file")
        if upload is None: return jsonify({"error":"請選擇 .pptx 範本。"}), 400
        path = None
        try:
            path = _validated_pptx_upload(upload, max_mb=int(os.environ.get("AI_PRESENTATION_TEMPLATE_MAX_MB","25") or 25))
            location = PresentationStorage().store(path, namespace="templates", object_id=f"tpl-{uuid.uuid4().hex}", filename=upload.filename or "template.pptx")
            raw_profile = request.form.get("layoutProfile") or "{}"
            profile = repository.sanitize_layout_profile(json.loads(raw_profile) if isinstance(raw_profile, str) else {})
            created = repository.create_template(
                name=str(request.form.get("name") or Path(upload.filename or "PowerPoint 範本").stem).strip()[:160],
                group_key=group, training_area=area, actor_username=str(user.get("username") or ""),
                storage_backend=location["backend"], storage_key=location["key"], storage_filename=location["filename"],
                sha256=location["sha256"], byte_size=location["byteSize"], mime_type=location["mimeType"], layout_profile=profile)
        except (ValueError, RuntimeError, json.JSONDecodeError) as exc:
            return jsonify({"error":str(exc)}), 400
        finally:
            if path: path.unlink(missing_ok=True)
        audit.record_event(actor=user, action="presentation.template.create", target_type="ai_presentation_template",
                           target_id=str(created.get("id") or ""), group=group,
                           after={"name":created.get("name"),"area":area,"sha256":created.get("sha256")})
        return jsonify({"ok":True,"template":_public_template(created)}), 201

    @app.post("/api/ai-presentations/generate")
    def presentation_generate():
        user = _actor(owner)
        if not user: return jsonify({"error":"請先登入。","loginRequired":True}), 401
        denied = _capability(user, "presentation.create", "目前角色不可建立 AI PowerPoint。")
        if denied: return denied
        body = request.get_json(silent=True) or {}; draft = media_script_repository.get_script(str(body.get("draftId") or ""))
        if not draft: return jsonify({"error":"找不到 AI 投影片草稿。"}), 404
        denied = _scope(owner, str(draft.get("group") or ""))
        if denied: return denied
        if draft.get("draftType") != "slides" or draft.get("status") != "approved":
            return jsonify({"error":"請先建立並由教師核准「投影片大綱」AI 草稿。"}), 409
        template_id = str(body.get("templateId") or "").strip()
        if template_id:
            template = repository.get_template(template_id)
            if not template or not template.get("active"): return jsonify({"error":"PowerPoint 範本不存在或已停用。"}), 404
            if template.get("group") != draft.get("group") or template.get("area") != draft.get("area"):
                return jsonify({"error":"只能使用同組、同訓練範圍的 PowerPoint 範本。"}), 403
        try:
            PresentationStorage().backend()
            slides = body.get("slides"); slides = ai_presentation_runtime.normalize_slides(slides) if isinstance(slides, list) else None
            job = ai_presentation_jobs.enqueue(draft=draft, template_id=template_id, actor_username=str(user.get("username") or ""), slides=slides)
        except (ValueError, RuntimeError) as exc:
            return jsonify({"error":str(exc)}), 400
        audit.record_event(actor=user, action="presentation.create", target_type="ai_presentation_job", target_id=str(job.get("id") or ""),
                           group=str(draft.get("group") or ""), detail={"draftId":draft.get("id"),"templateId":template_id,"ruleset":quality.RULESET_VERSION})
        return jsonify(ai_presentation_jobs.public_job(job)), 202

    @app.get("/api/ai-presentations/jobs/<job_id>")
    def presentation_job(job_id):
        user = _actor(owner)
        if not user: return jsonify({"error":"請先登入。","loginRequired":True}), 401
        denied = _capability(user, "presentation.edit", "目前角色不可查看 AI PowerPoint 工作。")
        if denied: return denied
        job = repository.get_job(str(job_id))
        if not job: return jsonify({"error":"找不到 PowerPoint 工作。"}), 404
        denied = _scope(owner, str(job.get("group") or ""))
        return denied if denied else jsonify(ai_presentation_jobs.public_job(job))

    @app.get("/api/ai-presentations")
    def presentation_list():
        user = _actor(owner)
        if not user: return jsonify({"error":"請先登入。","loginRequired":True}), 401
        denied = _capability(user, "presentation.edit", "目前角色不可查看 AI PowerPoint。")
        if denied: return denied
        group, material_id = str(request.args.get("group") or "").strip(), str(request.args.get("materialId") or "").strip()
        if material_id and not group:
            material = material_repository.get_material(material_id)
            if not material: return jsonify({"error":"找不到教材。"}), 404
            group = str(material.get("group") or "")
        if not group: group = str(user.get("preferredGroup") or user.get("preferred_group") or "").strip()
        if group:
            denied = _scope(owner, group)
            if denied: return denied
        return jsonify([_public_presentation(item) for item in repository.list_presentations(group_key=group, material_id=material_id)])

    def load_scoped(presentation_id: str, user, capability="presentation.edit"):
        denied = _capability(user, capability, "目前角色不可操作 AI PowerPoint。")
        if denied: return None, denied
        item = repository.get_presentation(str(presentation_id))
        if not item: return None, (jsonify({"error":"找不到 PowerPoint。"}), 404)
        denied = _scope(owner, str(item.get("group") or ""))
        return (None, denied) if denied else (item, None)

    @app.get("/api/ai-presentations/<presentation_id>")
    def presentation_get(presentation_id):
        user = _actor(owner)
        if not user: return jsonify({"error":"請先登入。","loginRequired":True}), 401
        item, denied = load_scoped(presentation_id, user)
        return denied if denied else jsonify(_public_presentation(item))

    @app.get("/api/ai-presentations/<presentation_id>/quality")
    def presentation_quality(presentation_id):
        user = _actor(owner)
        if not user: return jsonify({"error":"請先登入。","loginRequired":True}), 401
        item, denied = load_scoped(presentation_id, user)
        if denied: return denied
        manifest = _effective_quality(item)
        return jsonify({
            "presentationId": item.get("id"), "rulesetVersion": quality.RULESET_VERSION,
            "quality": manifest, "renderMetrics": _render_observability(item),
            "publishable": manifest.get("status") != "error",
            "requiresWarningAcknowledgement": manifest.get("status") == "warning",
        })

    @app.get("/api/ai-presentations/<presentation_id>/download")
    def presentation_download(presentation_id):
        user = _actor(owner)
        if not user: return jsonify({"error":"請先登入。","loginRequired":True}), 401
        item, denied = load_scoped(presentation_id, user)
        if denied: return denied
        if not _artifact_ready(item):
            return jsonify({"error":"PowerPoint artifact 尚未由 AI Worker 完成或 durable metadata 不完整。"}), 409
        try:
            download_name = safe_filename(f"{item.get('title') or 'AI教學投影片'}-r{item.get('revisionNumber') or 1}.pptx")
            response = PresentationStorage().browser_response(_artifact(item), download_name=download_name)
        except RuntimeError as exc:
            return jsonify({"error":str(exc)}), 503
        return send_file(response, as_attachment=True, download_name=download_name, mimetype=PPTX_MIME) if isinstance(response, Path) else response

    @app.get("/api/ai-presentations/<presentation_id>/provenance")
    def presentation_provenance(presentation_id):
        user = _actor(owner)
        if not user: return jsonify({"error":"請先登入。","loginRequired":True}), 401
        item, denied = load_scoped(presentation_id, user)
        if denied: return denied
        return jsonify({
            "presentationId": item.get("id"), "presentationFamilyId": item.get("presentationFamilyId"),
            "revisionNumber": item.get("revisionNumber"), "provenance": item.get("provenance") or {},
        })

    @app.get("/api/ai-presentations/<presentation_id>/history")
    def presentation_history(presentation_id):
        user = _actor(owner)
        if not user: return jsonify({"error":"請先登入。","loginRequired":True}), 401
        item, denied = load_scoped(presentation_id, user)
        if denied: return denied
        family = str(item.get("presentationFamilyId") or item.get("id") or "")
        history = repository.list_family_revisions(family)
        published = repository.latest_published(family)
        return jsonify({"presentationFamilyId": family, "currentPresentationId": item.get("id"),
                        "published": _public_presentation(published) if published else None,
                        "revisions": [_public_presentation(revision) for revision in history]})

    @app.get("/api/ai-presentation-families/<family_id>/published")
    def presentation_published(family_id):
        user = _actor(owner)
        if not user: return jsonify({"error":"請先登入。","loginRequired":True}), 401
        item = repository.latest_published(str(family_id))
        if not item: return jsonify({"error":"此 PowerPoint 尚無正式發布版本。"}), 404
        denied = _scope(owner, str(item.get("group") or ""))
        return denied if denied else jsonify(_public_presentation(item))

    @app.get("/api/ai-presentation-families/<family_id>/published/download")
    def presentation_published_download(family_id):
        user = _actor(owner)
        if not user: return jsonify({"error":"請先登入。","loginRequired":True}), 401
        item = repository.latest_published(str(family_id))
        if not item: return jsonify({"error":"此 PowerPoint 尚無正式發布版本。"}), 404
        denied = _scope(owner, str(item.get("group") or ""))
        if denied: return denied
        if not _artifact_ready(item): return jsonify({"error":"已發布 artifact metadata 不完整。"}), 409
        try:
            download_name = safe_filename(f"{item.get('title') or 'AI教學投影片'}-published-r{item.get('revisionNumber') or 1}.pptx")
            response = PresentationStorage().browser_response(_artifact(item), download_name=download_name)
        except RuntimeError as exc:
            return jsonify({"error":str(exc)}), 503
        return send_file(response, as_attachment=True, download_name=download_name, mimetype=PPTX_MIME) if isinstance(response, Path) else response

    @app.patch("/api/ai-presentations/<presentation_id>")
    def presentation_edit(presentation_id):
        user = _actor(owner)
        if not user: return jsonify({"error":"請先登入。","loginRequired":True}), 401
        current, denied = load_scoped(presentation_id, user)
        if denied: return denied
        body = request.get_json(silent=True) or {}; title = str(body.get("title") or current.get("title") or "AI 教學投影片").strip()[:255]
        slides = body.get("slides") if "slides" in body else current.get("slides")
        try:
            PresentationStorage().backend()
            normalized = ai_presentation_runtime.normalize_slides(slides)
            revision = repository.create_revision(current, actor_username=str(user.get("username") or ""), title=title, slides=normalized)
            job = ai_presentation_jobs.enqueue_revision(presentation=revision, actor_username=str(user.get("username") or ""))
        except (ValueError, RuntimeError) as exc:
            return jsonify({"error":str(exc)}), 400
        audit.record_event(actor=user, action="presentation.edit", target_type="ai_presentation", target_id=str(revision.get("id") or ""),
                           group=str(current.get("group") or ""), before={"revision":current.get("revisionNumber"),"status":current.get("status")},
                           after={"revision":revision.get("revisionNumber"),"status":revision.get("status")},
                           detail={"parentVersionId":current.get("id"),"renderJobId":job.get("id"),"renderedInWeb":False,"ruleset":quality.RULESET_VERSION})
        return jsonify({"ok":True,"presentation":_public_presentation(revision),"job":ai_presentation_jobs.public_job(job)}), 202

    @app.post("/api/ai-presentations/<presentation_id>/regenerate")
    def presentation_regenerate(presentation_id):
        user = _actor(owner)
        if not user: return jsonify({"error":"請先登入。","loginRequired":True}), 401
        current, denied = load_scoped(presentation_id, user)
        if denied: return denied
        try:
            PresentationStorage().backend()
            idempotency_key = quality.regenerate_key(current)
            existing_job = repository.get_job_by_idempotency_key(idempotency_key)
            if existing_job:
                target_id = str((existing_job.get("request") or {}).get("presentationId") or "")
                target = repository.get_presentation(target_id) if target_id else None
                return jsonify({"ok":True,"replayed":True,"presentation":_public_presentation(target or current),"job":ai_presentation_jobs.public_job(existing_job)}), 202
            normalized = ai_presentation_runtime.normalize_slides(list(current.get("slides") or []))
            revision = repository.create_revision(current, actor_username=str(user.get("username") or ""), slides=normalized)
            job = ai_presentation_jobs.enqueue_revision(
                presentation=revision, actor_username=str(user.get("username") or ""),
                idempotency_key=idempotency_key, regenerate=True,
            )
            provisional = _effective_quality(revision)
            repository.update_presentation_quality(
                str(revision.get("id") or ""), quality_manifest=provisional,
                render_metrics={"rulesetVersion":quality.RULESET_VERSION,"jobId":job.get("id"),"attempts":job.get("attempts",0)},
                render_ruleset_version=quality.RULESET_VERSION, actor_username=str(user.get("username") or ""),
            )
            revision = repository.get_presentation(str(revision.get("id") or "")) or revision
        except (ValueError, RuntimeError) as exc:
            return jsonify({"error":str(exc)}), 400
        audit.record_event(actor=user, action="presentation.regenerate", target_type="ai_presentation", target_id=str(revision.get("id") or ""),
                           group=str(current.get("group") or ""), detail={"sourcePresentationId":current.get("id"),"renderJobId":job.get("id"),"ruleset":quality.RULESET_VERSION})
        return jsonify({"ok":True,"replayed":False,"presentation":_public_presentation(revision),"job":ai_presentation_jobs.public_job(job)}), 202

    @app.post("/api/ai-presentations/jobs/<job_id>/retry")
    def presentation_retry_job(job_id):
        user = _actor(owner)
        if not user: return jsonify({"error":"請先登入。","loginRequired":True}), 401
        denied = _capability(user, "presentation.edit", "目前角色不可重試 AI PowerPoint 工作。")
        if denied: return denied
        job = repository.get_job(str(job_id))
        if not job: return jsonify({"error":"找不到 PowerPoint 工作。"}), 404
        denied = _scope(owner, str(job.get("group") or ""))
        if denied: return denied
        retried = ai_presentation_jobs.retry(job=job)
        if not retried: return jsonify({"error":"此工作不是可安全重試的失敗狀態，或已達重試上限。"}), 409
        audit.record_event(actor=user, action="presentation.retry", target_type="ai_presentation_job", target_id=str(job_id),
                           group=str(job.get("group") or ""), detail={"attempts": job.get("attempts"), "idempotentJobId": job_id})
        return jsonify(ai_presentation_jobs.public_job(retried)), 202

    @app.post("/api/ai-presentations/<presentation_id>/reupload")
    def presentation_reupload(presentation_id):
        user = _actor(owner)
        if not user: return jsonify({"error":"請先登入。","loginRequired":True}), 401
        current, denied = load_scoped(presentation_id, user)
        if denied: return denied
        upload = request.files.get("file")
        if upload is None: return jsonify({"error":"請選擇教師修正版 .pptx。"}), 400
        path = None
        try:
            path = _validated_pptx_upload(upload, max_mb=int(os.environ.get("AI_PRESENTATION_ARTIFACT_MAX_MB","50") or 50))
            family = str(current.get("presentationFamilyId") or current.get("id") or ""); revision_no = repository.next_revision_number(family)
            artifact = PresentationStorage().store(path, namespace="artifacts", object_id=f"{family}-r{revision_no}", filename=upload.filename or f"teacher-edit-r{revision_no}.pptx")
            revision = repository.create_revision(current, actor_username=str(user.get("username") or ""), artifact=artifact)
            manifest = _effective_quality(revision)
            manifest = quality.add_warning(manifest, "MANUAL_ARTIFACT_UNCHECKED", detail="教師上傳的 PPTX 未由 Worker 重新排版，發布前需人工確認版面。")
            repository.update_presentation_quality(
                str(revision.get("id") or ""), quality_manifest=manifest,
                render_metrics={"rulesetVersion":quality.RULESET_VERSION,"renderedSlideCount":manifest.get("slideCount",0)},
                render_ruleset_version=quality.RULESET_VERSION, actor_username=str(user.get("username") or ""),
            )
            revision = repository.get_presentation(str(revision.get("id") or "")) or revision
        except (ValueError, RuntimeError) as exc:
            return jsonify({"error":str(exc)}), 400
        finally:
            if path: path.unlink(missing_ok=True)
        audit.record_event(actor=user, action="presentation.edit", target_type="ai_presentation", target_id=str(revision.get("id") or ""),
                           group=str(current.get("group") or ""), detail={"parentVersionId":current.get("id"),"teacherPptxReupload":True,"qualityWarning":"MANUAL_ARTIFACT_UNCHECKED"})
        return jsonify({"ok":True,"presentation":_public_presentation(revision)}), 201

    @app.post("/api/ai-presentations/<presentation_id>/approve")
    def presentation_approve(presentation_id):
        user = _actor(owner)
        if not user: return jsonify({"error":"請先登入。","loginRequired":True}), 401
        denied = _teacher_approval(user)
        if denied: return denied
        current = repository.get_presentation(str(presentation_id))
        if not current: return jsonify({"error":"找不到 PowerPoint。"}), 404
        denied = _scope(owner, str(current.get("group") or ""))
        if denied: return denied
        if str(current.get("status") or "") not in {"draft","approved"}:
            return jsonify({"error":"只有 draft PowerPoint 可以核准。"}), 409
        if not _artifact_ready(current):
            return jsonify({"error":"PowerPoint artifact 尚未由 AI Worker 完成，不能核准。"}), 409
        try:
            approved = repository.set_status(str(presentation_id), status="approved", actor_username=str(user.get("username") or ""))
        except ValueError as exc:
            return jsonify({"error":str(exc)}), 409
        audit.record_event(actor=user, action="presentation.approve", target_type="ai_presentation", target_id=str(presentation_id),
                           group=str(current.get("group") or ""), before={"status":current.get("status")},
                           after={"status":"approved","approvedBy":(approved or {}).get("approvedBy"),"artifactSha256":current.get("artifactSha256"),"qualityStatus":_effective_quality(current).get("status")})
        return jsonify({"ok":True,"presentation":_public_presentation(approved or {})})

    @app.post("/api/ai-presentations/<presentation_id>/publish-link")
    def presentation_publish(presentation_id):
        user = _actor(owner)
        if not user: return jsonify({"error":"請先登入。","loginRequired":True}), 401
        denied = _publisher(user)
        if denied: return denied
        current = repository.get_presentation(str(presentation_id))
        if not current: return jsonify({"error":"找不到 PowerPoint。"}), 404
        denied = _scope(owner, str(current.get("group") or ""))
        if denied: return denied
        if str(current.get("status") or "") not in {"approved","published"}:
            return jsonify({"error":"PowerPoint 必須先由授課教師核准。"}), 409
        if not _artifact_ready(current):
            return jsonify({"error":"PowerPoint artifact durable metadata 不完整，不能發布。"}), 409
        body = request.get_json(silent=True) or {}
        manifest = _effective_quality(current)
        if manifest.get("status") == "error":
            return jsonify({"error":"發布前品質檢查有阻擋錯誤，請先重新產生或修正。","quality":manifest,"qualityBlocked":True}), 409
        warning_ack = None
        if manifest.get("status") == "warning":
            if body.get("acknowledgeWarnings") is not True:
                return jsonify({"error":"此版本有品質警告；請由授權發布者確認警告後再發布。","quality":manifest,"requiresWarningAcknowledgement":True}), 409
            warning_ack = {"actor":str(user.get("username") or ""),"at":dt.datetime.now(dt.timezone.utc).isoformat()}
            audit.record_event(actor=user, action="presentation.quality-warning-acknowledge", target_type="ai_presentation", target_id=str(current.get("id") or ""),
                               group=str(current.get("group") or ""), detail={"ruleset":manifest.get("rulesetVersion"),"warningCodes":[item.get("code") for item in manifest.get("warnings",[])]})
        material_id = str(body.get("publicationMaterialId") or "").strip()
        material = material_repository.get_material(material_id) if material_id else None
        if not material: return jsonify({"error":"找不到正式發布教材。"}), 404
        denied = _scope(owner, str(material.get("group") or ""))
        if denied: return denied
        if material.get("group") != current.get("group") or material.get("area") != current.get("area"):
            return jsonify({"error":"正式教材範圍與 PowerPoint 範圍不一致。"}), 409
        if not _durable_material(material):
            return jsonify({"error":"正式教材尚未保存到共享 durable provider，不能建立發布 receipt。"}), 409
        receipt = repository.create_publication(
            presentation_id=str(current.get("id") or ""), publication_material_id=material_id, actor_username=str(user.get("username") or ""),
            receipt={"presentationId":str(current.get("id") or ""),"presentationRevision":int(current.get("revisionNumber") or 1),
                     "presentationBackend":str(current.get("artifactBackend") or ""),"presentationStorageKey":str(current.get("artifactStorageKey") or ""),
                     "presentationSha256":str(current.get("artifactSha256") or ""),"presentationBytes":int(current.get("artifactBytes") or 0),
                     "presentationMimeType":str(current.get("artifactMimeType") or ""),"publicationMaterialId":material_id,
                     "publicationBackend":str(material.get("storageBackend") or ""),"publicationStorageKey":str(material.get("storageKey") or ""),
                     "qualityStatus":manifest.get("status"),"qualityRulesetVersion":manifest.get("rulesetVersion")},
            presentation_family_id=str(current.get("presentationFamilyId") or current.get("id") or ""),
            presentation_revision_number=int(current.get("revisionNumber") or 1), snapshot=_publication_snapshot(current, manifest=manifest, warning_ack=warning_ack))
        try:
            published = current if str(current.get("status") or "") == "published" else repository.set_status(
                str(current.get("id") or ""), status="published", actor_username=str(user.get("username") or "")
            )
        except ValueError as exc:
            return jsonify({"error":str(exc)}), 409
        audit.record_event(actor=user, action="presentation.publish", target_type="ai_presentation", target_id=str(current.get("id") or ""),
                           group=str(current.get("group") or ""), after={"status":"published","publicationMaterialId":material_id,"receiptKey":receipt.get("receiptKey"),"qualityStatus":manifest.get("status")})
        return jsonify({"ok":True,"presentation":_public_presentation(published or {}),"publicationReceipt":receipt})

    app.extensions["teacher_ai_presentation_routes_registered"] = True
    return app


__all__ = ["register_ai_presentation_routes", "_presentation_allowed", "_artifact_ready"]
