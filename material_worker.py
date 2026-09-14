# -*- coding: utf-8 -*-
"""V5.7.0 durable material worker.

The web request only receives the source file and creates a DB job. This worker
claims jobs from material_jobs, runs the existing trusted upload/conversion path
inside a separate process, and records completion / retry state.
"""
import os
import sys
import time
import json
import socket
import datetime
import tempfile
from pathlib import Path

import app as appmod
from media_processing_67 import ffmpeg_capability, libreoffice_capability
from upload_hardening import _magic_ok, _validate_zip_bytes, ZIP_EXT

WORKER_ID = os.environ.get("MATERIAL_WORKER_ID", "").strip() or f"{socket.gethostname()}:{os.getpid()}"


def log(message):
    print(f"[material-worker {WORKER_ID}] {message}", flush=True)


def _retry_at(attempts: int):
    delay = min(300, max(10, 15 * max(1, attempts)))
    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=delay)).isoformat(), delay


def _validate_downloaded_source(source: Path, job: dict):
    """Repeat the upload boundary checks after a cross-service download."""
    payload = dict(job.get("payload") or {})
    original = Path(payload.get("originalName") or job.get("originalName") or source.name).name
    ext = original.lower() and Path(original).suffix.lower()
    if ext not in appmod.ALLOWED_EXT:
        raise RuntimeError("Shared Staging 檔案副檔名不受支援。")
    if not source.is_file() or source.stat().st_size <= 0:
        raise RuntimeError("Shared Staging 原始檔不存在或空白。")
    expected_size = int(job.get("sourceBytes", 0) or 0)
    if expected_size and source.stat().st_size != expected_size:
        raise RuntimeError("Shared Staging 檔案大小不符，已拒絕處理。")
    if source.stat().st_size > appmod.MAX_UPLOAD_MB * 1024 * 1024:
        raise RuntimeError("Shared Staging 檔案超過上傳大小限制。")
    expected_hash = str(job.get("sourceSha256") or payload.get("sourceSha256") or "").lower()
    actual_hash = appmod._sha256_file(source)
    if not expected_hash or actual_hash != expected_hash:
        raise RuntimeError("Shared Staging SHA256 驗證失敗，已拒絕處理。")
    with source.open("rb") as fh:
        head = fh.read(8192)
    if not _magic_ok(ext, head):
        raise RuntimeError("Shared Staging 檔案內容與副檔名不符，已拒絕處理。")
    if ext in ZIP_EXT:
        _validate_zip_bytes(source.read_bytes(), ext)
    return original


def _post_sync_upload(job, source: Path, original: str):
    payload = dict(job.get("payload") or {})
    if not appmod.ADMIN_KEY:
        raise RuntimeError("ADMIN_KEY 未設定，背景 Worker 無法安全呼叫教材處理流程。")
    form = {
        "title": payload.get("title", ""),
        "desc": payload.get("desc", ""),
        "category": payload.get("category", ""),
        "group": payload.get("group", appmod.DEFAULT_GROUP),
        "area": payload.get("area", appmod.DEFAULT_TRAINING_AREA),
        "courseId": payload.get("courseId", ""),
        "materialType": payload.get("materialType", "standard"),
        "atlasCategory": payload.get("atlasCategory", ""),
        "atlasMagnification": payload.get("atlasMagnification", ""),
        "atlasInterpretation": payload.get("atlasInterpretation", ""),
        "atlasClinical": payload.get("atlasClinical", ""),
        "atlasDifferential": payload.get("atlasDifferential", ""),
        "atlasNormality": payload.get("atlasNormality", ""),
        "atlasTags": payload.get("atlasTags", ""),
        "progressId": job["id"],
        "materialId": payload.get("materialId") or job.get("materialId", ""),
        "sourceSha256": payload.get("sourceSha256") or job.get("sourceSha256", ""),
    }
    with source.open("rb") as fh:
        form["file"] = (fh, original)
        with appmod.app.test_client() as client:
            response = client.post(
                "/api/slides/upload",
                data=form,
                headers={"X-Admin-Key": appmod.ADMIN_KEY},
                content_type="multipart/form-data",
            )
            try:
                body = response.get_json(silent=True) or {}
            except Exception:
                body = {}
            if response.status_code < 200 or response.status_code >= 300:
                detail = "｜".join(str(body.get(k) or "").strip() for k in ("error", "stage", "detail") if body.get(k))
                raise RuntimeError(detail or f"教材背景處理失敗 (HTTP {response.status_code})")
            return body


def process_job(job):
    job_id = job["id"]
    attempts = int(job.get("attempts", 1) or 1)
    max_attempts = int(job.get("maxAttempts", appmod.MATERIAL_JOB_MAX_ATTEMPTS) or appmod.MATERIAL_JOB_MAX_ATTEMPTS)
    log(f"claim {job_id}, attempt {attempts}/{max_attempts}")
    appmod.sync_media_processing_metadata(job, "processing")

    # Idempotency: if a prior attempt committed the material but the process died
    # before updating job status, do not upload it again.
    material_id = job.get("materialId") or (job.get("payload") or {}).get("materialId", "")
    existing = appmod.get_material(material_id) if material_id else None
    if existing:
        now = appmod._utc_now_iso()
        appmod._update_material_job(
            job_id,
            status="completed",
            finished_at=now,
            stage="已完成",
            detail="偵測到教材已存在，背景工作自動續接完成狀態。",
            material_id=material_id,
            result=existing,
            error="",
        )
        appmod.delete_material_job_staging(job)
        appmod._update_material_job(job_id, staging_path="", staging_key="")
        appmod.sync_media_processing_metadata(job, "completed")
        appmod.set_upload_progress(job_id, 100, "教材建立完成", "教材已存在，背景工作狀態已自動修復。")
        return

    try:
        with tempfile.TemporaryDirectory(prefix="teacher-material-worker-") as temp_dir:
            payload = dict(job.get("payload") or {})
            original = Path(payload.get("originalName") or job.get("originalName") or "source.bin").name
            source = Path(temp_dir) / ("source" + Path(original).suffix.lower())
            appmod.download_material_job_staging(job, source)
            original = _validate_downloaded_source(source, job)
            result = _post_sync_upload(job, source, original)
        now = appmod._utc_now_iso()
        material_id = str(result.get("id") or material_id or "")
        appmod._update_material_job(
            job_id,
            status="completed",
            finished_at=now,
            stage="已完成",
            detail="轉檔、預覽最佳化、雲端儲存與資料庫同步皆完成。",
            material_id=material_id,
            result=result,
            error="",
        )
        appmod.set_upload_progress(job_id, 100, "教材建立完成", "背景工作已完成，可在教材清單開啟。")
        # The durable result is committed; successful jobs do not retain the
        # Shared Staging copy.  Retry/terminal failures intentionally retain it.
        appmod.delete_material_job_staging(job)
        appmod._update_material_job(job_id, staging_path="", staging_key="")
        appmod.sync_media_processing_metadata(job, "completed")
        log(f"completed {job_id} -> {material_id}")
    except Exception as exc:
        error = str(exc)[:1200]
        if attempts < max_attempts:
            available_at, delay = _retry_at(attempts)
            appmod._update_material_job(
                job_id,
                status="retry_wait",
                available_at=available_at,
                stage="等待自動重試",
                detail=f"本次失敗，{delay} 秒後使用同一份原始檔重試；不需要重新上傳。",
                error=error,
                worker_id="",
            )
            appmod.set_upload_progress(job_id, 8, "等待自動重試", f"{error}｜將自動重試，不需要重新上傳。")
            appmod.sync_media_processing_metadata(job, "retry_wait", error)
            log(f"retry {job_id}: {error}")
        else:
            now = appmod._utc_now_iso()
            appmod._update_material_job(
                job_id,
                status="failed",
                finished_at=now,
                stage="處理失敗",
                detail="已達自動重試上限；暫存原始檔仍保留，可由後台按『重新處理』。",
                error=error,
                worker_id="",
            )
            appmod.set_upload_progress(job_id, 0, "處理失敗", f"{error}｜原始檔暫時保留，可直接重新處理。")
            appmod.sync_media_processing_metadata(job, "failed", error)
            log(f"failed {job_id}: {error}")


def main():
    if not appmod.MATERIAL_BACKGROUND_JOBS:
        log("MATERIAL_BACKGROUND_JOBS=false; worker disabled")
        return 0
    if not appmod.MATERIAL_WORKER_ENABLED:
        log("MATERIAL_WORKER_ENABLED=false; worker disabled")
        return 0
    if not appmod.DATABASE_URL:
        log("DATABASE_URL is not set; using SQLite only for local development")
    if not appmod.ADMIN_KEY:
        log("ADMIN_KEY is required by the trusted in-process material handler")
        return 2
    try:
        conn, kind = appmod._db_conn()
        conn.execute("SELECT 1").fetchone()
        conn.close()
        log(f"database ready ({kind})")
    except Exception as exc:
        log(f"database unavailable: {exc}")
        return 2
    staging = appmod.shared_staging_capability()
    if not staging.get("available"):
        log("shared staging unavailable; worker will not start")
        return 2
    log(f"shared staging={staging.get('backend')} ffmpeg={ffmpeg_capability().get('available')} libreoffice={libreoffice_capability(appmod.SOFFICE_BIN).get('available')} adminKey=true")
    appmod.init_material_jobs_db()
    recovered = appmod.recover_stale_material_jobs()
    if recovered:
        log(f"recovered {recovered} stale job(s)")
    last_cleanup = 0.0
    while True:
        try:
            now = time.time()
            if now - last_cleanup > 900:
                appmod.cleanup_material_job_staging()
                last_cleanup = now
            job = appmod.claim_next_material_job(WORKER_ID)
            if not job:
                time.sleep(appmod.MATERIAL_JOB_POLL_SECONDS)
                continue
            process_job(job)
        except KeyboardInterrupt:
            log("stopping")
            return 0
        except Exception as exc:
            log(f"loop error: {exc}")
            time.sleep(max(2, appmod.MATERIAL_JOB_POLL_SECONDS))


if __name__ == "__main__":
    sys.exit(main())
