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
import shutil
import socket
import datetime
from pathlib import Path

import app as appmod

WORKER_ID = os.environ.get("MATERIAL_WORKER_ID", "").strip() or f"{socket.gethostname()}:{os.getpid()}"


def log(message):
    print(f"[material-worker {WORKER_ID}] {message}", flush=True)


def _retry_at(attempts: int):
    delay = min(300, max(10, 15 * max(1, attempts)))
    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=delay)).isoformat(), delay


def _post_sync_upload(job):
    payload = dict(job.get("payload") or {})
    source = Path(job.get("stagingPath") or "")
    if not source.exists() or source.stat().st_size <= 0:
        raise RuntimeError("背景工作暫存原始檔不存在或為空白，請重新上傳教材。")
    if not appmod.ADMIN_KEY:
        raise RuntimeError("ADMIN_KEY 未設定，背景 Worker 無法安全呼叫教材處理流程。")

    original = payload.get("originalName") or source.name
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
        appmod.set_upload_progress(job_id, 100, "教材建立完成", "教材已存在，背景工作狀態已自動修復。")
        return

    try:
        result = _post_sync_upload(job)
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
        # Success no longer needs the queued upload copy.
        staging = Path(job.get("stagingPath") or "")
        if staging.exists() and appmod.MATERIAL_JOB_DIR in staging.parents:
            shutil.rmtree(staging.parent, ignore_errors=True)
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
            log(f"failed {job_id}: {error}")


def main():
    if not appmod.MATERIAL_BACKGROUND_JOBS:
        log("MATERIAL_BACKGROUND_JOBS=false; worker disabled")
        return 0
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
