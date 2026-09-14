"""Teacher 6.7 B-Free API: remote local-worker control and R2 direct uploads.

The Web service owns PostgreSQL state.  A hospital/local worker reaches only
these narrowly-scoped HTTPS endpoints; it never needs a production DB login.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import math
import re
import threading
import time
import uuid
from pathlib import Path

from flask import jsonify, request, send_file


_RATE_LOCK = threading.Lock()
_RATE: dict[str, list[float]] = {}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _json_row(row):
    return dict(row) if row else {}


def _worker_id(value) -> str:
    return re.sub(r"[^A-Za-z0-9._:-]", "", str(value or ""))[:160]


def _worker_rate_ok() -> bool:
    key = str(request.remote_addr or "unknown")[:80]
    now = time.monotonic()
    with _RATE_LOCK:
        recent = [stamp for stamp in _RATE.get(key, []) if now - stamp < 60]
        if len(recent) >= 120:
            _RATE[key] = recent
            return False
        recent.append(now)
        _RATE[key] = recent
    return True


def _worker_auth(base):
    token = str(getattr(base, "MATERIAL_WORKER_TOKEN", "") or "")
    supplied = str(request.headers.get("Authorization", ""))
    expected = f"Bearer {token}"
    if not token or not hmac.compare_digest(supplied, expected):
        return jsonify({"error": "Worker token 無效或尚未設定。"}), 401
    if not _worker_rate_ok():
        return jsonify({"error": "Worker API 請求過於頻繁。"}), 429
    return None


def _worker_owned(base, job_id: str, worker_id: str):
    job = base.get_material_job(job_id, include_payload=True)
    if not job:
        return None, (jsonify({"error": "找不到背景教材工作。"}), 404)
    if job.get("status") != "processing" or not hmac.compare_digest(str(job.get("workerId") or ""), worker_id):
        return None, (jsonify({"error": "工作狀態或 Worker ownership 不符。"}), 409)
    return job, None


def _heartbeat(base, worker_id: str, capabilities=None, current_job_id=""):
    now = _now()
    capabilities = capabilities if isinstance(capabilities, dict) else {}
    conn, kind = base._db_conn(); ph = "%s" if kind == "postgres" else "?"
    try:
        raw = __import__("json").dumps(capabilities, ensure_ascii=False)
        if kind == "postgres":
            conn.execute("INSERT INTO material_worker_heartbeats(worker_id,last_seen,capabilities,current_job_id) VALUES(%s,%s,%s::jsonb,%s) ON CONFLICT(worker_id) DO UPDATE SET last_seen=EXCLUDED.last_seen,capabilities=EXCLUDED.capabilities,current_job_id=EXCLUDED.current_job_id", (worker_id, now, raw, current_job_id))
        else:
            conn.execute("INSERT INTO material_worker_heartbeats(worker_id,last_seen,capabilities,current_job_id) VALUES(?,?,?,?) ON CONFLICT(worker_id) DO UPDATE SET last_seen=excluded.last_seen,capabilities=excluded.capabilities,current_job_id=excluded.current_job_id", (worker_id, now, raw, current_job_id))
    finally:
        conn.close()
    if current_job_id:
        base._update_material_job(current_job_id, worker_last_seen=now)
    return now


def _safe_upload_filename(value) -> tuple[str, str]:
    filename = Path(str(value or "")).name
    ext = Path(filename).suffix.lower()
    if not filename or ext not in __import__("app").ALLOWED_EXT:
        raise ValueError("不支援此檔案格式。")
    return filename, ext


def _session(base, upload_id: str):
    conn, kind = base._db_conn(); ph = "%s" if kind == "postgres" else "?"
    try:
        return _json_row(conn.execute(f"SELECT * FROM material_upload_sessions WHERE id={ph}", (upload_id,)).fetchone())
    finally:
        conn.close()


def _update_session(base, upload_id: str, **fields):
    allowed = {"status", "updated_at", "r2_upload_id", "completed_parts"}
    clean = {k: v for k, v in fields.items() if k in allowed}
    if not clean:
        return
    clean.setdefault("updated_at", _now())
    conn, kind = base._db_conn(); ph = "%s" if kind == "postgres" else "?"
    try:
        vals = []
        sets = []
        for key, value in clean.items():
            sets.append(f"{key}={ph}")
            vals.append(value)
        vals.append(upload_id)
        conn.execute(f"UPDATE material_upload_sessions SET {', '.join(sets)} WHERE id={ph}", tuple(vals))
    finally:
        conn.close()


def _new_job_from_session(base, session):
    payload = _json_row(__import__("json").loads(session.get("payload") or "{}"))
    base.create_material_job(
        job_id=session["job_id"], payload=payload, staging_backend="r2",
        staging_key=session["staging_key"], staging_path="",
        source_sha256=session["source_sha256"], source_bytes=int(session["source_bytes"]),
        material_id=session["material_id"], original_name=session["original_name"],
    )
    base.sync_media_processing_metadata({"id": session["job_id"], "materialId": session["material_id"], "originalName": session["original_name"], "payload": payload}, "queued")


def register_free_worker(base):
    app = base.app
    if app.extensions.get("teacher_free_worker_67_registered"):
        return app

    @app.post("/api/material-worker/claim")
    def material_worker_claim():
        denied = _worker_auth(base)
        if denied: return denied
        body = request.get_json(silent=True) or {}
        worker_id = _worker_id(body.get("workerId"))
        if not worker_id: return jsonify({"error": "workerId 不合法。"}), 400
        _heartbeat(base, worker_id, body.get("capabilities"))
        job = base.claim_next_material_job(worker_id)
        if not job: return jsonify({"job": None})
        _heartbeat(base, worker_id, body.get("capabilities"), job["id"])
        response = {"id": job["id"], "workerId": worker_id, "attempts": job["attempts"], "maxAttempts": job["maxAttempts"], "materialId": job["materialId"], "originalName": job["originalName"], "sourceBytes": job["sourceBytes"], "sourceSha256": job["sourceSha256"], "payload": job.get("payload") or {}, "stagingBackend": job.get("stagingBackend")}
        if job.get("stagingBackend") == "r2":
            response["downloadUrl"] = base.r2_client().generate_presigned_url("get_object", Params={"Bucket": base.R2_BUCKET_NAME, "Key": job.get("stagingKey", "")}, ExpiresIn=base.MATERIAL_WORKER_URL_TTL_SECONDS)
        else:
            # Compatibility path for existing small Web uploads.  It is
            # deliberately token-protected and only proxies the already
            # claimed source; large production media uses the R2 URL above.
            response["downloadPath"] = f"/api/material-worker/{job['id']}/source"
        return jsonify({"job": response})

    @app.get("/api/material-worker/<job_id>/source")
    def material_worker_source(job_id):
        denied = _worker_auth(base)
        if denied: return denied
        worker_id = _worker_id(request.headers.get("X-Teacher-Worker-Id"))
        if not worker_id:
            return jsonify({"error": "缺少 Worker ID。"}), 400
        job, error = _worker_owned(base, job_id, worker_id)
        if error: return error
        # R2 jobs use an opaque short-lived presigned URL and must not make
        # the Web service proxy a large object.
        if str(job.get("stagingBackend") or "").lower() == "r2":
            return jsonify({"error": "R2 工作必須使用預簽下載網址。"}), 409
        temp = __import__("tempfile").NamedTemporaryFile(prefix="teacher-worker-source-", suffix=Path(str(job.get("originalName") or "")).suffix, delete=False)
        temp_path = Path(temp.name); temp.close()
        try:
            base.download_material_job_staging(job, temp_path)
        except Exception as exc:
            temp_path.unlink(missing_ok=True)
            return jsonify({"error": f"無法取得教材暫存檔：{str(exc)[:240]}"}), 503
        response = send_file(temp_path, as_attachment=True, download_name=Path(str(job.get("originalName") or "source")).name, max_age=0)
        # ``send_file`` keeps the descriptor open until the WSGI response is
        # closed; remove the short-lived relay file at that same boundary.
        response.call_on_close(lambda: temp_path.unlink(missing_ok=True))
        return response

    @app.post("/api/material-worker/heartbeat")
    @app.post("/api/material-worker/<job_id>/heartbeat")
    def material_worker_heartbeat(job_id=""):
        denied = _worker_auth(base)
        if denied: return denied
        body = request.get_json(silent=True) or {}; worker_id = _worker_id(body.get("workerId"))
        if not worker_id: return jsonify({"error": "workerId 不合法。"}), 400
        if job_id:
            _job, error = _worker_owned(base, job_id, worker_id)
            if error: return error
        return jsonify({"ok": True, "lastSeen": _heartbeat(base, worker_id, body.get("capabilities"), job_id)})

    def terminal(job_id, action):
        denied = _worker_auth(base)
        if denied: return denied
        body = request.get_json(silent=True) or {}; worker_id = _worker_id(body.get("workerId"))
        job, error = _worker_owned(base, job_id, worker_id)
        if error: return error
        detail = str(body.get("error") or "")[:1200]
        now = _now()
        if action == "complete":
            try:
                result = base.commit_material_job_result(job, body.get("result") if isinstance(body.get("result"), dict) else {})
            except (ValueError, TypeError) as exc:
                return jsonify({"error": str(exc)[:300]}), 400
            cleanup_pending = False
            try: base.delete_material_job_staging(job)
            except Exception: cleanup_pending = True
            base._update_material_job(job_id, status="completed", finished_at=now, stage="已完成", detail="本機 Worker 已完成教材處理與正式儲存。", result=result, error="", cleanup_pending=cleanup_pending, staging_path="", staging_key="" if not cleanup_pending else job.get("stagingKey", ""))
            base.sync_media_processing_metadata(job, "completed")
            return jsonify({"ok": True, "status": "completed", "cleanupPending": cleanup_pending})
        if action == "retry":
            attempts = int(job.get("attempts", 0) or 0); maximum = int(job.get("maxAttempts", 1) or 1)
            if attempts >= maximum:
                action = "fail"
            else:
                available, delay = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=min(300, max(10, attempts * 15)))).isoformat(), min(300, max(10, attempts * 15))
                base._update_material_job(job_id, status="retry_wait", available_at=available, stage="等待自動重試", detail=f"本機 Worker 回報暫時失敗；{delay} 秒後重試。", error=detail, worker_id="")
                base.sync_media_processing_metadata(job, "retry_wait", detail)
                return jsonify({"ok": True, "status": "retry_wait", "retryAfterSeconds": delay})
        base._update_material_job(job_id, status="failed", finished_at=now, stage="處理失敗", detail="本機 Worker 回報已達重試上限或不可恢復失敗。", error=detail, worker_id="")
        base.sync_media_processing_metadata(job, "failed", detail)
        return jsonify({"ok": True, "status": "failed"})

    @app.post("/api/material-worker/<job_id>/complete")
    def material_worker_complete(job_id): return terminal(job_id, "complete")
    @app.post("/api/material-worker/<job_id>/retry")
    def material_worker_retry(job_id): return terminal(job_id, "retry")
    @app.post("/api/material-worker/<job_id>/fail")
    def material_worker_fail(job_id): return terminal(job_id, "fail")

    @app.post("/api/material-upload/init")
    def material_upload_init():
        denied = base.require_admin()
        if denied: return denied
        if not base.MATERIAL_DIRECT_UPLOAD_ENABLED or not base.r2_is_configured():
            return jsonify({"error": "大型影音雲端直傳目前尚未設定", "available": False}), 409
        body = request.get_json(silent=True) or {}
        try:
            original, ext = _safe_upload_filename(body.get("filename"))
            size = int(body.get("size", 0) or 0)
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc) or "上傳資料格式錯誤。"}), 400
        limit = base.MATERIAL_DIRECT_UPLOAD_MAX_MB * 1024 * 1024
        if size <= 0 or size > limit: return jsonify({"error": "檔案大小超過直傳限制。"}), 400
        sha = str(body.get("sha256") or "").lower()
        if not re.fullmatch(r"[a-f0-9]{64}", sha): return jsonify({"error": "必須提供 SHA256。"}), 400
        part_size = max(8, min(32, int(body.get("partSizeMb", 16) or 16))) * 1024 * 1024
        part_count = int(math.ceil(size / part_size))
        if part_count > 10000: return jsonify({"error": "分段數量超過限制。"}), 400
        upload_id = "matup-" + uuid.uuid4().hex[:20]; job_id = "matjob-" + uuid.uuid4().hex[:16]; material_id = "upload-" + hashlib.sha256(job_id.encode()).hexdigest()[:12]
        key = f"_staging/material-jobs/{job_id}/source{ext}"
        metadata = {"jobid": job_id, "originalname": original, "expectedbytes": str(size), "sha256": sha, "createdat": _now()}
        r2_upload_id = ""
        try:
            multipart = base.r2_client().create_multipart_upload(Bucket=base.R2_BUCKET_NAME, Key=key, ContentType=base._content_type_for(original), Metadata=metadata)
            r2_upload_id = str(multipart["UploadId"])
            payload = {"originalName": original, "sourceMime": base._content_type_for(original), "title": str(body.get("title") or "")[:255], "desc": str(body.get("desc") or "")[:1000], "category": str(body.get("category") or "")[:100], "group": base.normalize_group(body.get("group", base.DEFAULT_GROUP)), "area": base.normalize_area(body.get("area", base.DEFAULT_TRAINING_AREA)), "courseId": str(body.get("courseId") or "")[:100], "materialType": str(body.get("materialType") or "standard")[:40], "materialId": material_id, "sourceSha256": sha}
            conn, kind = base._db_conn(); ph = "%s" if kind == "postgres" else "?"
            try:
                raw = __import__("json").dumps(payload, ensure_ascii=False)
                if kind == "postgres": conn.execute("INSERT INTO material_upload_sessions(id,job_id,material_id,staging_key,original_name,source_sha256,source_bytes,r2_upload_id,part_size,expected_parts,payload,status,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)", (upload_id, job_id, material_id, key, original, sha, size, r2_upload_id, part_size, part_count, raw, "uploading", _now(), _now()))
                else: conn.execute("INSERT INTO material_upload_sessions(id,job_id,material_id,staging_key,original_name,source_sha256,source_bytes,r2_upload_id,part_size,expected_parts,payload,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (upload_id, job_id, material_id, key, original, sha, size, r2_upload_id, part_size, part_count, raw, "uploading", _now(), _now()))
            finally: conn.close()
        except Exception as exc:
            try: base.r2_client().abort_multipart_upload(Bucket=base.R2_BUCKET_NAME, Key=key, UploadId=r2_upload_id)
            except Exception: pass
            return jsonify({"error": f"無法建立雲端直傳工作：{str(exc)[:300]}"}), 503
        urls = [{"partNumber": n, "url": base.r2_client().generate_presigned_url("upload_part", Params={"Bucket": base.R2_BUCKET_NAME, "Key": key, "UploadId": r2_upload_id, "PartNumber": n}, ExpiresIn=base.MATERIAL_WORKER_URL_TTL_SECONDS)} for n in range(1, part_count + 1)]
        return jsonify({"uploadId": upload_id, "jobId": job_id, "materialId": material_id, "partSize": part_size, "parts": urls, "expiresIn": base.MATERIAL_WORKER_URL_TTL_SECONDS}), 201

    @app.post("/api/material-upload/<upload_id>/complete")
    def material_upload_complete(upload_id):
        denied = base.require_admin()
        if denied: return denied
        session = _session(base, upload_id)
        if not session or session.get("status") != "uploading": return jsonify({"error": "上傳工作不存在或已完成。"}), 404
        body = request.get_json(silent=True) or {}; parts = body.get("parts")
        if not isinstance(parts, list) or len(parts) != int(session["expected_parts"]): return jsonify({"error": "multipart parts 不完整。"}), 400
        normalized=[]
        for expected, part in enumerate(parts, 1):
            if not isinstance(part, dict) or int(part.get("partNumber", 0) or 0) != expected or not str(part.get("etag") or "").strip(): return jsonify({"error": "multipart part 格式錯誤。"}), 400
            normalized.append({"PartNumber": expected, "ETag": str(part["etag"])})
        try:
            base.r2_client().complete_multipart_upload(Bucket=base.R2_BUCKET_NAME, Key=session["staging_key"], UploadId=session["r2_upload_id"], MultipartUpload={"Parts": normalized})
            head = base.r2_client().head_object(Bucket=base.R2_BUCKET_NAME, Key=session["staging_key"])
            if int(head.get("ContentLength", -1)) != int(session["source_bytes"]): raise ValueError("R2 物件大小驗證失敗。")
            if str((head.get("Metadata") or {}).get("sha256", "")).lower() != str(session["source_sha256"]).lower(): raise ValueError("R2 物件 metadata 驗證失敗。")
            try: _new_job_from_session(base, session)
            except Exception:
                base.r2_client().delete_object(Bucket=base.R2_BUCKET_NAME, Key=session["staging_key"])
                raise
            _update_session(base, upload_id, status="completed", completed_parts=__import__("json").dumps(normalized))
        except Exception as exc:
            return jsonify({"error": f"直傳完成驗證失敗：{str(exc)[:300]}"}), 400
        return jsonify({"accepted": True, "jobId": session["job_id"], "status": "queued"}), 202

    @app.post("/api/material-upload/<upload_id>/abort")
    def material_upload_abort(upload_id):
        denied = base.require_admin()
        if denied: return denied
        session = _session(base, upload_id)
        if not session: return jsonify({"error": "找不到上傳工作。"}), 404
        if session.get("status") == "uploading":
            try: base.r2_client().abort_multipart_upload(Bucket=base.R2_BUCKET_NAME, Key=session["staging_key"], UploadId=session["r2_upload_id"])
            except Exception: pass
            _update_session(base, upload_id, status="aborted")
        return jsonify({"ok": True})

    app.extensions["teacher_free_worker_67_registered"] = True
    return app
