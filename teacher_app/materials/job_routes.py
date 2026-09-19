"""Canonical HTTP owner for material background-job administration."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import mimetypes
import tempfile
import uuid
from pathlib import Path

from flask import jsonify, request

from teacher_app.auth import rbac_legacy_adapter
from teacher_app.common import scope
from teacher_app.config import max_upload_mb
from teacher_app.materials.job_runtime import MaterialJobRuntime, from_compat_owner
from teacher_app.materials.validation import ALLOWED_MATERIAL_EXTENSIONS, normalize_material_filename
from teacher_app.worker import repository as worker_repository


ALLOWED_EXT = ALLOWED_MATERIAL_EXTENSIONS


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _content_type_for(path_or_name) -> str:
    return mimetypes.guess_type(str(path_or_name))[0] or "application/octet-stream"


def _material_job_priority(source_bytes: int) -> int:
    megabytes = max(0, int(source_bytes or 0)) / 1024 / 1024
    if megabytes <= 25:
        return 100
    if megabytes <= 100:
        return 70
    return 40


def _runtime_for(owner, app, runtime: MaterialJobRuntime | None) -> MaterialJobRuntime:
    if runtime is not None:
        return runtime
    configured = app.extensions.get("teacher_material_job_runtime")
    if configured is not None:
        return configured
    if owner is not app:
        return from_compat_owner(owner)
    raise RuntimeError("material job routes require an explicit MaterialJobRuntime")


def _guard(app):
    return rbac_legacy_adapter.legacy_admin_guard(app)


def _runtime_bool(value) -> bool:
    return bool(value() if callable(value) else value)


def _runtime_int(value) -> int:
    return int(value() if callable(value) else value)


def register_material_job_routes(owner, *, runtime: MaterialJobRuntime | None = None):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_material_job_routes_registered"):
        return app
    runtime = _runtime_for(owner, app, runtime)
    app.extensions["teacher_material_job_runtime"] = runtime
    connection_factory = runtime.connection_factory

    def api_upload_progress(progress_id):
        denied = _guard(app)
        if denied:
            return denied
        path = runtime.progress_path(progress_id)
        if not path or not path.exists():
            return jsonify({"percent": 0, "stage": "等待上傳開始", "detail": ""})
        try:
            return jsonify(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return jsonify({"percent": 0, "stage": "讀取進度中", "detail": ""})

    def api_list_material_jobs():
        denied = _guard(app)
        if denied:
            return denied
        try:
            limit = int(request.args.get("limit", 30) or 30)
        except Exception:
            limit = 30
        runtime.cleanup_budget_state()
        ops = runtime.operations_status()
        return jsonify({
            "jobs": worker_repository.list_material_jobs(limit, connection_factory=connection_factory),
            "backgroundEnabled": _runtime_bool(runtime.background_enabled),
            "workerEnabled": _runtime_bool(runtime.worker_enabled),
            "queueBackend": "material_jobs",
            "staging": runtime.staging_capability(),
            "workers": ops.get("workers", []),
            "pendingJobs": ops.get("pendingJobs", 0),
            "processingJobs": ops.get("processingJobs", 0),
            "retryJobs": ops.get("retryJobs", 0),
            "failedJobs": ops.get("failedJobs", 0),
            "r2Budget": ops.get("r2Budget", {}),
        })

    def api_get_material_job(job_id):
        denied = _guard(app)
        if denied:
            return denied
        job = worker_repository.get_material_job(
            job_id,
            include_payload=False,
            connection_factory=connection_factory,
        )
        if not job:
            return jsonify({"error": "找不到此背景教材工作"}), 404
        return jsonify(job)

    def api_enqueue_material_job():
        denied = _guard(app)
        if denied:
            return denied
        if not _runtime_bool(runtime.web_byte_upload_enabled):
            return jsonify({
                "error": "Web 檔案接收相容路徑已關閉；請使用 Browser → R2 直傳。",
                "directUploadRequired": True,
            }), 409
        if not _runtime_bool(runtime.background_enabled):
            return jsonify({"error": "背景教材佇列未啟用，請改用同步上傳端點。"}), 409
        if "file" not in request.files:
            return jsonify({"error": "未收到檔案"}), 400
        upload = request.files["file"]
        try:
            original_name, ext = normalize_material_filename(upload.filename or "untitled")
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        job_id = f"matjob-{uuid.uuid4().hex[:16]}"
        material_id = "upload-" + hashlib.sha256(job_id.encode("utf-8")).hexdigest()[:12]
        staging_record = None
        try:
            with tempfile.TemporaryDirectory(prefix="teacher-material-upload-") as temp_dir:
                staged = Path(temp_dir) / f"source{ext}"
                upload.save(str(staged))
                source_bytes = staged.stat().st_size
                if source_bytes <= 0:
                    raise ValueError("教材檔案為空白檔案")
                if source_bytes > max_upload_mb() * 1024 * 1024:
                    raise ValueError("教材檔案超過上傳大小限制。")
                source_sha256 = _sha256_file(staged)
                payload = {
                    "originalName": original_name,
                    "sourceMime": _content_type_for(original_name),
                    "title": request.form.get("title", "").strip()[:255],
                    "desc": request.form.get("desc", "").strip()[:1000],
                    "category": request.form.get("category", "").strip()[:100],
                    "group": scope.normalize_group(request.form.get("group", scope.DEFAULT_GROUP)),
                    "area": scope.normalize_area(request.form.get("area", scope.DEFAULT_TRAINING_AREA)),
                    "courseId": request.form.get("courseId", "").strip()[:100],
                    "materialType": request.form.get("materialType", "standard").strip().lower(),
                    "atlasCategory": request.form.get("atlasCategory", "").strip()[:120],
                    "atlasMagnification": request.form.get("atlasMagnification", "").strip()[:80],
                    "atlasInterpretation": request.form.get("atlasInterpretation", "").strip()[:1000],
                    "atlasClinical": request.form.get("atlasClinical", "").strip()[:1000],
                    "atlasDifferential": request.form.get("atlasDifferential", "").strip()[:1000],
                    "atlasNormality": request.form.get("atlasNormality", "").strip()[:40],
                    "atlasTags": request.form.get("atlasTags", "").strip()[:300],
                    "materialId": material_id,
                    "sourceSha256": source_sha256,
                }
                staging_backend, staging_key, staging_path = runtime.upload_staging(
                    staged,
                    job_id,
                    original_name,
                )
                staging_record = {
                    "stagingBackend": staging_backend,
                    "stagingKey": staging_key,
                    "stagingPath": staging_path,
                }
                try:
                    now = _utc_now_iso()
                    worker_repository.create_material_job(
                        {
                            "id": job_id,
                            "status": "queued",
                            "priority": _material_job_priority(source_bytes),
                            "created_at": now,
                            "updated_at": now,
                            "available_at": now,
                            "max_attempts": _runtime_int(runtime.max_attempts),
                            "stage": "等待背景處理",
                            "detail": "教材已安全接收，可離開此頁；獨立背景 Worker 會繼續。",
                            "payload": payload,
                            "staging_path": str(staging_path or ""),
                            "staging_backend": staging_backend,
                            "staging_key": staging_key,
                            "original_name": original_name,
                            "material_id": material_id,
                            "source_sha256": source_sha256,
                            "source_bytes": int(source_bytes or 0),
                        },
                        connection_factory=connection_factory,
                    )
                    runtime.sync_media_processing_metadata(
                        {
                            "id": job_id,
                            "materialId": material_id,
                            "originalName": original_name,
                            "payload": payload,
                        },
                        "queued",
                    )
                except Exception:
                    runtime.delete_staging(staging_record)
                    staging_record = None
                    raise
            runtime.clear_progress(job_id)
            runtime.set_progress(
                job_id,
                9,
                "已加入背景佇列",
                "教材已安全接收，可離開此頁；背景 Worker 將自動轉檔、最佳化並送往雲端。",
            )
            return jsonify({
                "accepted": True,
                "jobId": job_id,
                "materialId": material_id,
                "status": "queued",
                "sourceBytes": source_bytes,
                "sourceSha256": source_sha256,
                "statusUrl": f"/api/material-jobs/{job_id}",
                "message": "教材已安全接收並加入背景佇列，可離開此頁。",
            }), 202
        except Exception as exc:
            if staging_record:
                runtime.delete_staging(staging_record)
            return jsonify({"error": f"教材排隊失敗：{exc}"}), 400

    def api_retry_material_job(job_id):
        denied = _guard(app)
        if denied:
            return denied
        job = worker_repository.get_material_job(
            job_id,
            include_payload=True,
            connection_factory=connection_factory,
        )
        if not job:
            return jsonify({"error": "找不到此背景教材工作"}), 404
        if job.get("status") not in {"failed", "cancelled"}:
            return jsonify({"error": "只有失敗或已取消的工作可以重新處理"}), 409
        if not runtime.staging_exists(job):
            return jsonify({"error": "暫存原始檔已過期或不存在，請重新上傳教材。"}), 410
        now = _utc_now_iso()
        runtime.clear_progress(job_id)
        worker_repository.update_material_job(
            job_id,
            fields={
                "status": "queued",
                "updated_at": now,
                "available_at": now,
                "finished_at": "",
                "attempts": 0,
                "error": "",
                "stage": "重新排隊",
                "detail": "使用既有原始檔重新處理，不需要重新上傳；自動重試次數已重新計算",
                "cancel_requested": False,
                "worker_id": "",
            },
            connection_factory=connection_factory,
        )
        runtime.set_progress(job_id, 9, "重新排隊", "保留既有原始檔，等待背景 Worker 重新處理。")
        return jsonify({
            "ok": True,
            "job": worker_repository.get_material_job(
                job_id,
                connection_factory=connection_factory,
            ),
        })

    def api_cancel_material_job(job_id):
        denied = _guard(app)
        if denied:
            return denied
        job = worker_repository.get_material_job(
            job_id,
            include_payload=True,
            connection_factory=connection_factory,
        )
        if not job:
            return jsonify({"error": "找不到此背景教材工作"}), 404
        if job.get("status") == "processing":
            return jsonify({"error": "此工作已進入 LibreOffice／雲端處理階段，為避免留下半成品，請等待本次工作完成或失敗後再處理。"}), 409
        if job.get("status") in {"completed", "cancelled"}:
            return jsonify({
                "ok": True,
                "job": worker_repository.get_material_job(
                    job_id,
                    connection_factory=connection_factory,
                ),
            })
        now = _utc_now_iso()
        worker_repository.update_material_job(
            job_id,
            fields={
                "status": "cancelled",
                "updated_at": now,
                "finished_at": now,
                "cancel_requested": True,
                "stage": "已取消",
                "detail": "工作在開始轉檔前由管理者取消",
                "worker_id": "",
            },
            connection_factory=connection_factory,
        )
        runtime.set_progress(job_id, 0, "已取消", "教材背景工作已取消；暫存原始檔會依保留期限自動清理。")
        return jsonify({
            "ok": True,
            "job": worker_repository.get_material_job(
                job_id,
                connection_factory=connection_factory,
            ),
        })

    for rule, endpoint, view, methods in (
        ("/api/slides/upload-progress/<progress_id>", "api_upload_progress", api_upload_progress, ["GET"]),
        ("/api/material-jobs", "api_list_material_jobs", api_list_material_jobs, ["GET"]),
        ("/api/material-jobs/<job_id>", "api_get_material_job", api_get_material_job, ["GET"]),
        ("/api/material-jobs/upload", "api_enqueue_material_job", api_enqueue_material_job, ["POST"]),
        ("/api/material-jobs/<job_id>/retry", "api_retry_material_job", api_retry_material_job, ["POST"]),
        ("/api/material-jobs/<job_id>/cancel", "api_cancel_material_job", api_cancel_material_job, ["POST"]),
    ):
        app.add_url_rule(rule, endpoint=endpoint, view_func=view, methods=methods)

    app.extensions["teacher_material_job_routes_registered"] = True
    return app


__all__ = ["ALLOWED_EXT", "MaterialJobRuntime", "register_material_job_routes"]
