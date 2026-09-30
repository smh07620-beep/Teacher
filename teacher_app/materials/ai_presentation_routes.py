"""Teacher-facing APIs for reviewed AI PowerPoint authoring."""
from __future__ import annotations

import os
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
from teacher_app.materials.ai_presentation_storage import PPTX_MIME, PresentationStorage
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
    keys = ("id","name","group","area","active","sha256","byteSize","mimeType","createdBy","createdAt","updatedAt")
    return {key: item.get(key) for key in keys}


def _public_presentation(item: dict) -> dict:
    keys = (
        "id","presentationFamilyId","parentVersionId","revisionNumber","materialId","draftId","templateId",
        "group","area","title","status","slides","artifactSha256","artifactBytes","artifactMimeType",
        "provider","model","sourceJobId","createdBy","updatedBy","approvedBy","approvedAt","publishedAt",
        "createdAt","updatedAt",
    )
    return {key: item.get(key) for key in keys}


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
    return {"backend": item.get("artifactBackend"), "key": item.get("artifactStorageKey"), "sha256": item.get("artifactSha256")}


def _durable_material(material: dict) -> bool:
    return str(material.get("storageBackend") or "").lower() in {"r2","oci","gdrive","mega"} and bool(str(material.get("storageKey") or "").strip())


def register_ai_presentation_routes(owner):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_ai_presentation_routes_registered"):
        return app

    @app.get("/api/ai-presentations/status")
    def presentation_status():
        user = _actor(owner)
        if not user:
            return jsonify({"error":"請先登入。","loginRequired":True}), 401
        return jsonify({
            "storage": PresentationStorage().capability(), "workerRequired": True,
            "requiresApprovedSlideDraft": True, "teacherApprovalRoles": sorted(_TEACHER_APPROVAL_ROLES),
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
            if denied:
                return denied
        if area:
            try:
                area = scope.validate_area(area, default=None)
            except ValueError as exc:
                return jsonify({"error":str(exc)}), 400
        return jsonify([_public_template(item) for item in repository.list_templates(group_key=group, training_area=area)])

    @app.post("/api/ai-presentation-templates")
    def template_upload():
        user = _actor(owner)
        if not user:
            return jsonify({"error":"請先登入。","loginRequired":True}), 401
        group, area = str(request.form.get("group") or "").strip(), str(request.form.get("area") or "").strip()
        try:
            group, area = scope.validate_group(group, default=None), scope.validate_area(area, default=None)
        except ValueError as exc:
            return jsonify({"error":str(exc)}), 400
        denied = _scope(owner, group)
        if denied:
            return denied
        upload = request.files.get("file")
        if upload is None:
            return jsonify({"error":"請選擇 .pptx 範本。"}), 400
        path = None
        try:
            path = _validated_pptx_upload(upload, max_mb=int(os.environ.get("AI_PRESENTATION_MAX_TEMPLATE_MB","20") or 20))
            location = PresentationStorage().store(path, namespace="templates", object_id=f"tpl-{uuid.uuid4().hex}", filename=upload.filename or "template.pptx")
            created = repository.create_template(
                name=str(request.form.get("name") or Path(upload.filename or "PowerPoint 範本").stem).strip()[:160],
                group_key=group, training_area=area, actor_username=str(user.get("username") or ""),
                storage_backend=location["backend"], storage_key=location["key"], storage_filename=location["filename"],
                sha256=location["sha256"], byte_size=location["byteSize"], mime_type=location["mimeType"],
            )
        except (ValueError, RuntimeError) as exc:
            return jsonify({"error":str(exc)}), 400
        finally:
            if path:
                path.unlink(missing_ok=True)
        audit.record_event(actor=user, action="presentation.template.create", target_type="ai_presentation_template",
                           target_id=str(created.get("id") or ""), group=group,
                           after={"name":created.get("name"),"area":area,"sha256":created.get("sha256")})
        return jsonify({"ok":True,"template":_public_template(created)}), 201

    @app.post("/api/ai-presentations/generate")
    def presentation_generate():
        user = _actor(owner)
        if not user:
            return jsonify({"error":"請先登入。","loginRequired":True}), 401
        denied = _capability(user, "presentation.create", "目前角色不可建立 AI PowerPoint。")
        if denied:
            return denied
        body = request.get_json(silent=True) or {}
        draft = media_script_repository.get_script(str(body.get("draftId") or ""))
        if not draft:
            return jsonify({"error":"找不到 AI 投影片草稿。"}), 404
        denied = _scope(owner, str(draft.get("group") or ""))
        if denied:
            return denied
        if draft.get("draftType") != "slides" or draft.get("status") != "approved":
            return jsonify({"error":"請先建立並由教師核准「投影片大綱」AI 草稿。"}), 409
        template_id = str(body.get("templateId") or "").strip()
        if template_id:
            template = repository.get_template(template_id)
            if not template or not template.get("active"):
                return jsonify({"error":"PowerPoint 範本不存在或已停用。"}), 404
            if template.get("group") != draft.get("group") or template.get("area") != draft.get("area"):
                return jsonify({"error":"只能使用同組、同訓練範圍的 PowerPoint 範本。"}), 403
        try:
            PresentationStorage().backend()
            slides = body.get("slides")
            slides = ai_presentation_runtime.normalize_slides(slides) if isinstance(slides, list) else None
            job = ai_presentation_jobs.enqueue(draft=draft, template_id=template_id,
                                               actor_username=str(user.get("username") or ""), slides=slides)
        except (ValueError, RuntimeError) as exc:
            return jsonify({"error":str(exc)}), 400
        audit.record_event(actor=user, action="presentation.create", target_type="ai_presentation_job",
                           target_id=str(job.get("id") or ""), group=str(draft.get("group") or ""),
                           detail={"draftId":draft.get("id"),"templateId":template_id})
        return jsonify(ai_presentation_jobs.public_job(job)), 202

    @app.get("/api/ai-presentations/jobs/<job_id>")
    def presentation_job(job_id):
        user = _actor(owner)
        if not user:
            return jsonify({"error":"請先登入。","loginRequired":True}), 401
        denied = _capability(user, "presentation.edit", "目前角色不可查看 AI PowerPoint 工作。")
        if denied:
            return denied
        job = repository.get_job(str(job_id))
        if not job:
            return jsonify({"error":"找不到 PowerPoint 工作。"}), 404
        denied = _scope(owner, str(job.get("group") or ""))
        return denied if denied else jsonify(ai_presentation_jobs.public_job(job))

    @app.get("/api/ai-presentations")
    def presentation_list():
        user = _actor(owner)
        if not user:
            return jsonify({"error":"請先登入。","loginRequired":True}), 401
        denied = _capability(user, "presentation.edit", "目前角色不可查看 AI PowerPoint。")
        if denied:
            return denied
        group, material_id = str(request.args.get("group") or "").strip(), str(request.args.get("materialId") or "").strip()
        if material_id and not group:
            material = material_repository.get_material(material_id)
            if not material:
                return jsonify({"error":"找不到教材。"}), 404
            group = str(material.get("group") or "")
        if not group:
            group = str(user.get("preferredGroup") or user.get("preferred_group") or "").strip()
        if group:
            denied = _scope(owner, group)
            if denied:
                return denied
        return jsonify([_public_presentation(item) for item in repository.list_presentations(group_key=group, material_id=material_id)])

    def load_scoped(presentation_id: str, user, capability="presentation.edit"):
        denied = _capability(user, capability, "目前角色不可操作 AI PowerPoint。")
        if denied:
            return None, denied
        item = repository.get_presentation(str(presentation_id))
        if not item:
            return None, (jsonify({"error":"找不到 PowerPoint。"}), 404)
        denied = _scope(owner, str(item.get("group") or ""))
        return (None, denied) if denied else (item, None)

    @app.get("/api/ai-presentations/<presentation_id>")
    def presentation_get(presentation_id):
        user = _actor(owner)
        if not user:
            return jsonify({"error":"請先登入。","loginRequired":True}), 401
        item, denied = load_scoped(presentation_id, user)
        return denied if denied else jsonify(_public_presentation(item))

    @app.get("/api/ai-presentations/<presentation_id>/download")
    def presentation_download(presentation_id):
        user = _actor(owner)
        if not user:
            return jsonify({"error":"請先登入。","loginRequired":True}), 401
        item, denied = load_scoped(presentation_id, user)
        if denied:
            return denied
        try:
            response = PresentationStorage().browser_response(_artifact(item), download_name=f"{item.get('title') or 'AI教學投影片'}-r{item.get('revisionNumber') or 1}.pptx")
        except RuntimeError as exc:
            return jsonify({"error":str(exc)}), 503
        return send_file(response, as_attachment=True, download_name=response.name, mimetype=PPTX_MIME) if isinstance(response, Path) else response

    @app.patch("/api/ai-presentations/<presentation_id>")
    def presentation_edit(presentation_id):
        user = _actor(owner)
        if not user:
            return jsonify({"error":"請先登入。","loginRequired":True}), 401
        current, denied = load_scoped(presentation_id, user)
        if denied:
            return denied
        body = request.get_json(silent=True) or {}
        title = str(body.get("title") or current.get("title") or "AI 教學投影片").strip()[:255]
        slides = body.get("slides") if "slides" in body else current.get("slides")
        try:
            revision = ai_presentation_runtime.rerender_revision(current, actor_username=str(user.get("username") or ""), title=title, slides=slides)
        except (ValueError, RuntimeError) as exc:
            return jsonify({"error":str(exc)}), 400
        audit.record_event(actor=user, action="presentation.edit", target_type="ai_presentation",
                           target_id=str(revision.get("id") or ""), group=str(current.get("group") or ""),
                           before={"revision":current.get("revisionNumber"),"status":current.get("status")},
                           after={"revision":revision.get("revisionNumber"),"status":revision.get("status")},
                           detail={"parentVersionId":current.get("id")})
        return jsonify({"ok":True,"presentation":_public_presentation(revision)}), 201

    @app.post("/api/ai-presentations/<presentation_id>/reupload")
    def presentation_reupload(presentation_id):
        user = _actor(owner)
        if not user:
            return jsonify({"error":"請先登入。","loginRequired":True}), 401
        current, denied = load_scoped(presentation_id, user)
        if denied:
            return denied
        upload = request.files.get("file")
        if upload is None:
            return jsonify({"error":"請選擇教師修正版 .pptx。"}), 400
        path = None
        try:
            path = _validated_pptx_upload(upload, max_mb=int(os.environ.get("AI_PRESENTATION_MAX_ARTIFACT_MB","50") or 50))
            family = str(current.get("presentationFamilyId") or current.get("id") or "")
            revision_no = repository.next_revision_number(family)
            artifact = PresentationStorage().store(path, namespace="artifacts", object_id=f"{family}-r{revision_no}", filename=upload.filename or f"teacher-edit-r{revision_no}.pptx")
            revision = repository.create_revision(current, actor_username=str(user.get("username") or ""), artifact=artifact)
        except (ValueError, RuntimeError) as exc:
            return jsonify({"error":str(exc)}), 400
        finally:
            if path:
                path.unlink(missing_ok=True)
        audit.record_event(actor=user, action="presentation.edit", target_type="ai_presentation",
                           target_id=str(revision.get("id") or ""), group=str(current.get("group") or ""),
                           detail={"parentVersionId":current.get("id"),"teacherPptxReupload":True})
        return jsonify({"ok":True,"presentation":_public_presentation(revision)}), 201

    @app.post("/api/ai-presentations/<presentation_id>/approve")
    def presentation_approve(presentation_id):
        user = _actor(owner)
        if not user:
            return jsonify({"error":"請先登入。","loginRequired":True}), 401
        denied = _teacher_approval(user)
        if denied:
            return denied
        current = repository.get_presentation(str(presentation_id))
        if not current:
            return jsonify({"error":"找不到 PowerPoint。"}), 404
        denied = _scope(owner, str(current.get("group") or ""))
        if denied:
            return denied
        approved = repository.set_status(str(presentation_id), status="approved", actor_username=str(user.get("username") or ""))
        audit.record_event(actor=user, action="presentation.approve", target_type="ai_presentation",
                           target_id=str(presentation_id), group=str(current.get("group") or ""),
                           before={"status":current.get("status")}, after={"status":"approved","approvedBy":(approved or {}).get("approvedBy")})
        return jsonify({"ok":True,"presentation":_public_presentation(approved or {})})

    @app.post("/api/ai-presentations/<presentation_id>/publish-link")
    def presentation_publish(presentation_id):
        user = _actor(owner)
        if not user:
            return jsonify({"error":"請先登入。","loginRequired":True}), 401
        denied = _publisher(user)
        if denied:
            return denied
        current = repository.get_presentation(str(presentation_id))
        if not current:
            return jsonify({"error":"找不到 PowerPoint。"}), 404
        denied = _scope(owner, str(current.get("group") or ""))
        if denied:
            return denied
        if str(current.get("status") or "") not in {"approved","published"}:
            return jsonify({"error":"PowerPoint 必須先由授課教師核准。"}), 409
        material_id = str((request.get_json(silent=True) or {}).get("publicationMaterialId") or "").strip()
        material = material_repository.get_material(material_id) if material_id else None
        if not material:
            return jsonify({"error":"找不到正式發布教材。"}), 404
        denied = _scope(owner, str(material.get("group") or ""))
        if denied:
            return denied
        if material.get("group") != current.get("group") or material.get("area") != current.get("area"):
            return jsonify({"error":"正式教材範圍與 PowerPoint 範圍不一致。"}), 409
        if not _durable_material(material):
            return jsonify({"error":"正式教材尚未保存到共享 durable provider，不能建立發布 receipt。"}), 409
        receipt = repository.create_publication(
            presentation_id=str(current.get("id") or ""), publication_material_id=material_id,
            actor_username=str(user.get("username") or ""),
            receipt={"presentationId":str(current.get("id") or ""),"presentationRevision":int(current.get("revisionNumber") or 1),
                     "presentationSha256":str(current.get("artifactSha256") or ""),"publicationMaterialId":material_id,
                     "publicationBackend":str(material.get("storageBackend") or ""),"publicationStorageKey":str(material.get("storageKey") or "")},
        )
        published = repository.set_status(str(current.get("id") or ""), status="published", actor_username=str(user.get("username") or ""))
        audit.record_event(actor=user, action="presentation.publish", target_type="ai_presentation",
                           target_id=str(current.get("id") or ""), group=str(current.get("group") or ""),
                           after={"status":"published","publicationMaterialId":material_id,"receiptKey":receipt.get("receiptKey")})
        return jsonify({"ok":True,"presentation":_public_presentation(published or {}),"publicationReceipt":receipt})

    app.extensions["teacher_ai_presentation_routes_registered"] = True
    return app


__all__ = ["register_ai_presentation_routes", "_presentation_allowed"]
