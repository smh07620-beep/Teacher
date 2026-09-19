"""Canonical HTTP routes for the local material-worker protocol and R2 direct uploads.

The Web service owns PostgreSQL state.  A hospital/local worker reaches only
these narrowly-scoped HTTPS endpoints; it never needs a production DB login.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import math
import mimetypes
import re
import threading
import time
import uuid
from pathlib import Path

from flask import g, jsonify, request, send_file

from teacher_app.common import scope, scope_filter
from teacher_app.learning.routes import auto_index_material
from teacher_app.materials.validation import normalize_material_filename
from teacher_app.worker import protocol as worker_protocol
from teacher_app.worker import repository as worker_repository
from teacher_app.worker.web_runtime import WorkerWebRuntime, runtime_from_owner


_RATE_LOCK = threading.Lock()
_RATE: dict[str, list[float]] = {}
PART_HASH_STRATEGY = "sha256-parts-v1"
SINGLE_HASH_STRATEGY = "sha256-single-v1"
SINGLE_PUT_MAX_BYTES = 32 * 1024 * 1024


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


# Compatibility exports for existing callers/tests.  Implementation ownership
# is canonical in teacher_app.worker.protocol.
_worker_id = worker_protocol.normalize_worker_id
_worker_metadata = worker_protocol.sanitize_metadata


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


def _runtime_value(value):
    return value() if callable(value) else value


def _worker_auth(runtime: WorkerWebRuntime):
    token = str(_runtime_value(runtime.worker_token) or "")
    supplied = str(request.headers.get("Authorization", ""))
    if not worker_protocol.bearer_token_matches(token, supplied):
        return jsonify({"error": "Worker token 無效或尚未設定。"}), 401
    if not _worker_rate_ok():
        return jsonify({"error": "Worker API 請求過於頻繁。"}), 429
    return None


def _worker_owned(runtime: WorkerWebRuntime, job_id: str, worker_id: str):
    job = worker_repository.get_material_job(
        job_id,
        include_payload=True,
        connection_factory=runtime.connection_factory,
    )
    if not job:
        return None, (jsonify({"error": "找不到背景教材工作。"}), 404)
    if job.get("status") != "processing" or not hmac.compare_digest(str(job.get("workerId") or ""), worker_id):
        return None, (jsonify({"error": "工作狀態或 Worker ownership 不符。"}), 409)
    return job, None


def _heartbeat(runtime: WorkerWebRuntime, worker_id: str, capabilities=None, current_job_id="", metadata=None):
    return worker_protocol.record_heartbeat(
        worker_id,
        capabilities=capabilities,
        current_job_id=current_job_id,
        metadata=metadata,
        touch_job=lambda job_id, seen: worker_repository.touch_owned_material_job(
            job_id,
            worker_id,
            seen_at=seen,
            connection_factory=runtime.connection_factory,
        ),
        connection_factory=runtime.connection_factory,
    )


def _safe_upload_filename(value) -> tuple[str, str]:
    return normalize_material_filename(value)


def _session(runtime: WorkerWebRuntime, upload_id: str):
    return worker_repository.get_upload_session(
        upload_id,
        connection_factory=runtime.connection_factory,
    ) or {}


def _list_r2_parts(runtime: WorkerWebRuntime, session) -> list[dict]:
    """Read the authoritative multipart state directly from R2, including pagination."""

    client = runtime.r2_client_factory()
    bucket = str(_runtime_value(runtime.r2_bucket_name) or "")
    marker = None
    remote_parts: list[dict] = []
    while True:
        kwargs = {
            "Bucket": bucket,
            "Key": session["staging_key"],
            "UploadId": session["r2_upload_id"],
        }
        if marker is not None:
            kwargs["PartNumberMarker"] = marker
        page = client.list_parts(**kwargs)
        remote_parts.extend(page.get("Parts") or [])
        if not page.get("IsTruncated"):
            break
        next_marker = page.get("NextPartNumberMarker")
        if next_marker in (None, ""):
            if not remote_parts:
                raise RuntimeError("R2 multipart list_parts 分頁資訊不完整。")
            next_marker = max(int(part.get("PartNumber", 0) or 0) for part in remote_parts)
        marker = int(next_marker)
    return worker_protocol.normalize_remote_multipart_parts(
        remote_parts,
        session["expected_parts"],
    )


def _public_r2_parts(parts) -> list[dict]:
    return [
        {
            "partNumber": int(part.get("PartNumber", 0) or 0),
            "size": int(part.get("Size", 0) or 0),
        }
        for part in parts
    ]


def _fail_upload(runtime: WorkerWebRuntime, session, reason: str, *, delete_object=False, terminal=True):
    """Terminally release a direct-upload reservation without leaking R2 data."""
    if terminal and session.get("r2_upload_id"):
        try:
            runtime.r2_client_factory().abort_multipart_upload(Bucket=str(_runtime_value(runtime.r2_bucket_name) or ""), Key=session["staging_key"], UploadId=session["r2_upload_id"])
        except Exception:
            pass
    if delete_object:
        try:
            runtime.r2_client_factory().delete_object(Bucket=str(_runtime_value(runtime.r2_bucket_name) or ""), Key=session["staging_key"])
            runtime.record_r2_deleted(session["staging_key"])
        except Exception:
            pass
    if terminal:
        worker_repository.cas_upload_session_status(
            session["id"],
            expected_status=str(session.get("status") or "uploading"),
            new_status="failed",
            updated_at=_now(),
            connection_factory=runtime.connection_factory,
        )
    runtime.release_reservation(session["id"], reason)


def _job_record_from_session(runtime: WorkerWebRuntime, session):
    payload = dict(session.get("payload") or {})
    now = _now()
    source_bytes = int(session["source_bytes"])
    megabytes = max(0, source_bytes) / 1024 / 1024
    priority = 100 if megabytes <= 25 else (70 if megabytes <= 100 else 40)
    return {
        "id": session["job_id"],
        "status": "queued",
        "priority": priority,
        "created_at": now,
        "updated_at": now,
        "available_at": now,
        "max_attempts": int(_runtime_value(runtime.max_attempts) or 3),
        "stage": "等待背景處理",
        "detail": "教材已安全接收，可離開此頁；獨立背景 Worker 會繼續。",
        "payload": payload,
        "staging_path": "",
        "staging_backend": "r2",
        "staging_key": session["staging_key"],
        "original_name": session["original_name"],
        "material_id": session["material_id"],
        "source_sha256": session["source_sha256"],
        "source_bytes": int(session["source_bytes"]),
    }


def _content_type_for(path_or_name) -> str:
    return mimetypes.guess_type(str(path_or_name))[0] or "application/octet-stream"


def _ascii_metadata(metadata) -> dict[str, str]:
    return {
        str(key).encode("ascii", "backslashreplace").decode("ascii")[:1024]:
        str(value).encode("ascii", "backslashreplace").decode("ascii")[:1024]
        for key, value in dict(metadata or {}).items()
    }


def _runtime_for(owner, app, runtime: WorkerWebRuntime | None) -> WorkerWebRuntime:
    if runtime is not None:
        return runtime
    configured = app.extensions.get("teacher_worker_web_runtime")
    if configured is not None:
        return configured
    if owner is not app:
        return runtime_from_owner(owner)
    raise RuntimeError("worker routes require an explicit WorkerWebRuntime")


def register_free_worker(owner, *, runtime: WorkerWebRuntime | None = None):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_free_worker_67_registered"):
        return app
    compat_owner = owner if owner is not app and runtime is None else None
    runtime = _runtime_for(owner, app, runtime)
    app.extensions["teacher_worker_web_runtime"] = runtime

    def admin_guard():
        compat_admin_guard = getattr(compat_owner, "require_admin", None)
        if callable(compat_admin_guard):
            return compat_admin_guard()
        return scope_filter.require_permission(app, "material.manage")

    def current_actor():
        actor = getattr(g, "teacher_user", None)
        if actor is not None:
            return actor
        resolver = getattr(compat_owner, "_current_user", None)
        return resolver() if callable(resolver) else None

    def upload_session_guard(session):
        payload = dict(session.get("payload") or {})
        group = str(payload.get("group") or "").strip()
        _actor, denied = scope_filter.scoped_groups(
            compat_owner or app,
            "material.manage",
            {group} if group else set(),
        )
        if denied:
            return denied
        expected_username = str(payload.get("uploadActor") or "").strip()
        actor_username = str((current_actor() or {}).get("username") or "").strip()
        if expected_username and (
            not actor_username
            or not hmac.compare_digest(expected_username, actor_username)
        ):
            return jsonify({"error": "此上傳工作屬於另一個登入工作階段。"}), 403
        return None

    def normalize_resume_identity(body, session):
        stored = dict((session.get("payload") or {}).get("uploadIdentity") or {})
        if not stored:
            raise ValueError("此上傳工作建立時未啟用安全續傳，請重新建立上傳工作。")
        supplied_name, _ext = _safe_upload_filename(body.get("filename"))
        supplied = worker_protocol.normalize_client_file_identity(
            filename=supplied_name,
            size=body.get("size"),
            last_modified=body.get("lastModified"),
            fingerprint=body.get("fingerprint"),
            strategy=body.get("fingerprintStrategy"),
            part_size=body.get("fingerprintPartSize"),
            required=True,
        )
        if not worker_protocol.client_file_identity_matches(stored, supplied):
            raise ValueError("續傳檔案識別不符，已拒絕使用舊的上傳工作。")
        return supplied

    @app.post("/api/material-worker/claim")
    def material_worker_claim():
        denied = _worker_auth(runtime)
        if denied: return denied
        body = request.get_json(silent=True) or {}
        worker_id = _worker_id(body.get("workerId"))
        if not worker_id: return jsonify({"error": "workerId 不合法。"}), 400
        runtime.cleanup_budget_state()
        _heartbeat(runtime, worker_id, body.get("capabilities"), metadata=body)
        job = worker_repository.claim_next_material_job(
            worker_id,
            now=_now(),
            connection_factory=runtime.connection_factory,
        )
        if not job: return jsonify({"job": None})
        _heartbeat(runtime, worker_id, body.get("capabilities"), job["id"], body)
        response = {"id": job["id"], "workerId": worker_id, "attempts": job["attempts"], "maxAttempts": job["maxAttempts"], "materialId": job["materialId"], "originalName": job["originalName"], "sourceBytes": job["sourceBytes"], "sourceSha256": job["sourceSha256"], "payload": job.get("payload") or {}, "stagingBackend": job.get("stagingBackend")}
        if job.get("stagingBackend") == "r2":
            response["downloadUrl"] = runtime.r2_client_factory().generate_presigned_url("get_object", Params={"Bucket": str(_runtime_value(runtime.r2_bucket_name) or ""), "Key": job.get("stagingKey", "")}, ExpiresIn=int(_runtime_value(runtime.worker_url_ttl_seconds)))
        else:
            # Compatibility path for existing small Web uploads.  It is
            # deliberately token-protected and only proxies the already
            # claimed source; large production media uses the R2 URL above.
            response["downloadPath"] = f"/api/material-worker/{job['id']}/source"
        return jsonify({"job": response})

    @app.get("/api/material-worker/<job_id>/source")
    def material_worker_source(job_id):
        denied = _worker_auth(runtime)
        if denied: return denied
        worker_id = _worker_id(request.headers.get("X-Teacher-Worker-Id"))
        if not worker_id:
            return jsonify({"error": "缺少 Worker ID。"}), 400
        job, error = _worker_owned(runtime, job_id, worker_id)
        if error: return error
        # R2 jobs use an opaque short-lived presigned URL and must not make
        # the Web service proxy a large object.
        if str(job.get("stagingBackend") or "").lower() == "r2":
            return jsonify({"error": "R2 工作必須使用預簽下載網址。"}), 409
        temp = __import__("tempfile").NamedTemporaryFile(prefix="teacher-worker-source-", suffix=Path(str(job.get("originalName") or "")).suffix, delete=False)
        temp_path = Path(temp.name); temp.close()
        try:
            runtime.download_staging(job, temp_path)
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
        denied = _worker_auth(runtime)
        if denied: return denied
        body = request.get_json(silent=True) or {}; worker_id = _worker_id(body.get("workerId"))
        if not worker_id: return jsonify({"error": "workerId 不合法。"}), 400
        if job_id:
            _job, error = _worker_owned(runtime, job_id, worker_id)
            if error: return error
        return jsonify({"ok": True, "lastSeen": _heartbeat(runtime, worker_id, body.get("capabilities"), job_id, body)})

    def terminal(job_id, action):
        denied = _worker_auth(runtime)
        if denied: return denied
        body = request.get_json(silent=True) or {}; worker_id = _worker_id(body.get("workerId"))
        job, error = _worker_owned(runtime, job_id, worker_id)
        if error: return error
        detail = str(body.get("error") or "")[:1200]
        now = _now()
        if action == "complete":
            try:
                result = runtime.commit_result(job, body.get("result") if isinstance(body.get("result"), dict) else {})
            except (ValueError, TypeError) as exc:
                return jsonify({"error": str(exc)[:300]}), 400
            cleanup_pending = False
            try: runtime.delete_staging(job)
            except Exception: cleanup_pending = True
            updated = worker_repository.transition_owned_material_job(
                job_id,
                worker_id,
                fields={
                    "status": "completed",
                    "finished_at": now,
                    "updated_at": now,
                    "stage": "已完成",
                    "detail": "本機 Worker 已完成教材處理與正式儲存。",
                    "result": result,
                    "error": "",
                    "cleanup_pending": cleanup_pending,
                    "staging_path": "",
                    "staging_key": "" if not cleanup_pending else job.get("stagingKey", ""),
                },
                connection_factory=runtime.connection_factory,
            )
            if not updated:
                return jsonify({"error": "工作狀態或 Worker ownership 不符。"}), 409
            runtime.sync_media_processing_metadata(job, "completed")
            # Indexing is best-effort and deliberately occurs after the job is
            # terminal; it cannot delay heartbeats or alter restart semantics.
            try:
                auto_index_material(app, str(result.get("id") or job.get("materialId") or ""))
            except Exception:
                pass
            return jsonify({"ok": True, "status": "completed", "cleanupPending": cleanup_pending})
        if action == "retry":
            retry = worker_protocol.retry_plan(
                job.get("attempts", 0),
                job.get("maxAttempts", 1),
                stamp=now,
            )
            if not retry["retry"]:
                action = "fail"
            else:
                delay = int(retry["delaySeconds"])
                updated = worker_repository.transition_owned_material_job(
                    job_id,
                    worker_id,
                    fields={
                        "status": "retry_wait",
                        "available_at": retry["availableAt"],
                        "updated_at": now,
                        "stage": "等待自動重試",
                        "detail": f"本機 Worker 回報暫時失敗；{delay} 秒後重試。",
                        "error": detail,
                        "worker_id": "",
                    },
                    connection_factory=runtime.connection_factory,
                )
                if not updated:
                    return jsonify({"error": "工作狀態或 Worker ownership 不符。"}), 409
                runtime.sync_media_processing_metadata(job, "retry_wait", detail)
                return jsonify({"ok": True, "status": "retry_wait", "retryAfterSeconds": delay})
        updated = worker_repository.transition_owned_material_job(
            job_id,
            worker_id,
            fields={
                "status": "failed",
                "finished_at": now,
                "updated_at": now,
                "stage": "處理失敗",
                "detail": "本機 Worker 回報已達重試上限或不可恢復失敗。",
                "error": detail,
                "worker_id": "",
            },
            connection_factory=runtime.connection_factory,
        )
        if not updated:
            return jsonify({"error": "工作狀態或 Worker ownership 不符。"}), 409
        runtime.sync_media_processing_metadata(job, "failed", detail)
        return jsonify({"ok": True, "status": "failed"})

    @app.post("/api/material-worker/<job_id>/complete")
    def material_worker_complete(job_id): return terminal(job_id, "complete")
    @app.post("/api/material-worker/<job_id>/retry")
    def material_worker_retry(job_id): return terminal(job_id, "retry")
    @app.post("/api/material-worker/<job_id>/fail")
    def material_worker_fail(job_id): return terminal(job_id, "fail")

    @app.post("/api/material-upload/init")
    def material_upload_init():
        denied = admin_guard()
        if denied: return denied
        if not bool(_runtime_value(runtime.direct_upload_enabled)) or not runtime.r2_is_configured():
            return jsonify({"error": "大型影音雲端直傳目前尚未設定", "available": False}), 409
        body = request.get_json(silent=True) or {}
        try:
            original, ext = _safe_upload_filename(body.get("filename"))
            size = int(body.get("size", 0) or 0)
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc) or "上傳資料格式錯誤。"}), 400
        limit = int(_runtime_value(runtime.direct_upload_max_mb)) * 1024 * 1024
        if size <= 0 or size > limit: return jsonify({"error": "檔案大小超過直傳限制。"}), 400
        sha = str(body.get("sha256") or "").lower()
        hash_strategy = str(body.get("hashStrategy") or "").strip().lower()
        if sha and not re.fullmatch(r"[a-f0-9]{64}", sha):
            return jsonify({"error": "SHA256 格式錯誤。"}), 400
        if not sha and hash_strategy not in {PART_HASH_STRATEGY, SINGLE_HASH_STRATEGY}:
            return jsonify({"error": "必須提供 SHA256 或支援的分段雜湊策略。"}), 400
        part_size = max(8, min(32, int(body.get("partSizeMb", 16) or 16))) * 1024 * 1024
        upload_mode = "single" if size <= SINGLE_PUT_MAX_BYTES else "multipart"
        part_count = 1 if upload_mode == "single" else int(math.ceil(size / part_size))
        if part_count > 10000: return jsonify({"error": "分段數量超過限制。"}), 400
        upload_identity = {}
        try:
            if upload_mode == "multipart" and any(
                body.get(key) not in (None, "")
                for key in ("fingerprint", "fingerprintStrategy", "lastModified", "fingerprintPartSize")
            ):
                upload_identity = worker_protocol.normalize_client_file_identity(
                    filename=original,
                    size=size,
                    last_modified=body.get("lastModified"),
                    fingerprint=body.get("fingerprint"),
                    strategy=body.get("fingerprintStrategy"),
                    part_size=body.get("fingerprintPartSize"),
                    required=True,
                )
                if int(upload_identity["partSize"]) != part_size:
                    raise ValueError("續傳檔案指紋分段大小與上傳工作不符。")
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        upload_id = "matup-" + uuid.uuid4().hex[:20]; job_id = "matjob-" + uuid.uuid4().hex[:16]; material_id = "upload-" + hashlib.sha256(job_id.encode()).hexdigest()[:12]
        key = f"_staging/material-jobs/{job_id}/source{ext}"
        # The filename remains in PostgreSQL/session payloads.  S3 metadata
        # must be ASCII-only, so it deliberately contains no raw filename.
        integrity_mode = "sha256" if sha else (SINGLE_HASH_STRATEGY if upload_mode == "single" else PART_HASH_STRATEGY)
        integrity_metadata = {"sha256": sha} if sha else {"hashstrategy": integrity_mode}
        metadata = _ascii_metadata({"jobid": job_id, "expectedbytes": str(size), **integrity_metadata, "createdat": _now()})
        r2_upload_id = ""
        try:
            runtime.enforce_large_upload_budget(upload_id, key, size)
            if upload_mode == "multipart":
                multipart = runtime.r2_client_factory().create_multipart_upload(Bucket=str(_runtime_value(runtime.r2_bucket_name) or ""), Key=key, ContentType=_content_type_for(original), Metadata=metadata)
                r2_upload_id = str(multipart["UploadId"])
            actor_username = str((current_actor() or {}).get("username") or "").strip()[:100]
            payload = {"originalName": original, "sourceMime": _content_type_for(original), "title": str(body.get("title") or "")[:255], "desc": str(body.get("desc") or "")[:1000], "category": str(body.get("category") or "")[:100], "group": scope.normalize_group(body.get("group", scope.DEFAULT_GROUP)), "area": scope.normalize_area(body.get("area", scope.DEFAULT_TRAINING_AREA)), "courseId": str(body.get("courseId") or "")[:100], "materialType": str(body.get("materialType") or "standard")[:40], "atlasCategory": str(body.get("atlasCategory") or "").strip()[:120], "atlasMagnification": str(body.get("atlasMagnification") or "").strip()[:80], "atlasInterpretation": str(body.get("atlasInterpretation") or "").strip()[:1000], "atlasClinical": str(body.get("atlasClinical") or "").strip()[:1000], "atlasDifferential": str(body.get("atlasDifferential") or "").strip()[:1000], "atlasNormality": str(body.get("atlasNormality") or "").strip()[:40], "atlasTags": str(body.get("atlasTags") or "").strip()[:300], "materialId": material_id, "sourceSha256": sha, "integrityMode": integrity_mode, "uploadMode": upload_mode, "uploadActor": actor_username, "uploadIdentity": upload_identity}
            now = _now()
            worker_repository.create_upload_session(
                {
                    "id": upload_id,
                    "job_id": job_id,
                    "material_id": material_id,
                    "staging_key": key,
                    "original_name": original,
                    "source_sha256": sha,
                    "source_bytes": size,
                    "r2_upload_id": r2_upload_id,
                    "part_size": size if upload_mode == "single" else part_size,
                    "expected_parts": part_count,
                    "payload": payload,
                    "status": "uploading",
                    "created_at": now,
                    "updated_at": now,
                },
                connection_factory=runtime.connection_factory,
            )
        except Exception as exc:
            if r2_upload_id:
                try: runtime.r2_client_factory().abort_multipart_upload(Bucket=str(_runtime_value(runtime.r2_bucket_name) or ""), Key=key, UploadId=r2_upload_id)
                except Exception: pass
            runtime.release_reservation(upload_id, "init_failed")
            status = 409 if isinstance(exc, ValueError) else 503
            return jsonify({"error": f"無法建立雲端直傳工作：{str(exc)[:300]}"}), status
        ttl = int(_runtime_value(runtime.worker_url_ttl_seconds))
        if upload_mode == "single":
            url = runtime.r2_client_factory().generate_presigned_url("put_object", Params={"Bucket": str(_runtime_value(runtime.r2_bucket_name) or ""), "Key": key}, ExpiresIn=ttl)
            # Keep a one-item parts shape for older direct clients while the
            # canonical client uses the explicit server-selected mode/url.
            urls = [{"partNumber": 1, "url": url}]
            return jsonify({"mode": "single", "uploadId": upload_id, "jobId": job_id, "materialId": material_id, "partSize": size, "parts": urls, "url": url, "singlePutMaxBytes": SINGLE_PUT_MAX_BYTES, "expiresIn": ttl}), 201
        urls = [{"partNumber": n, "url": runtime.r2_client_factory().generate_presigned_url("upload_part", Params={"Bucket": str(_runtime_value(runtime.r2_bucket_name) or ""), "Key": key, "UploadId": r2_upload_id, "PartNumber": n}, ExpiresIn=ttl)} for n in range(1, part_count + 1)]
        return jsonify({"mode": "multipart", "uploadId": upload_id, "jobId": job_id, "materialId": material_id, "partSize": part_size, "expectedParts": part_count, "parts": urls, "uploadedParts": [], "expiresIn": ttl, "resumable": bool(upload_identity)}), 201

    @app.get("/api/material-upload/<upload_id>/status")
    def material_upload_status(upload_id):
        denied = admin_guard()
        if denied: return denied
        session = _session(runtime, upload_id)
        if not session:
            return jsonify({"error": "找不到上傳工作。"}), 404
        denied = upload_session_guard(session)
        if denied: return denied
        payload = dict(session.get("payload") or {})
        mode = str(payload.get("uploadMode") or ("multipart" if session.get("r2_upload_id") else "single"))
        response = {
            "mode": mode,
            "uploadId": session["id"],
            "jobId": session["job_id"],
            "materialId": session["material_id"],
            "status": str(session.get("status") or ""),
            "partSize": int(session.get("part_size") or 0),
            "expectedParts": int(session.get("expected_parts") or 0),
            "resumable": bool(payload.get("uploadIdentity")),
        }
        if mode != "multipart" or session.get("status") != "uploading":
            response["uploadedParts"] = []
            response["missingPartNumbers"] = []
            return jsonify(response)
        try:
            remote_parts = _list_r2_parts(runtime, session)
        except Exception as exc:
            return jsonify({"error": f"無法讀取 R2 multipart 狀態：{str(exc)[:240]}"}), 503
        response["uploadedParts"] = _public_r2_parts(remote_parts)
        response["missingPartNumbers"] = worker_protocol.missing_multipart_part_numbers(
            remote_parts,
            session["expected_parts"],
        )
        return jsonify(response)

    @app.post("/api/material-upload/<upload_id>/resume")
    def material_upload_resume(upload_id):
        denied = admin_guard()
        if denied: return denied
        session = _session(runtime, upload_id)
        if not session:
            return jsonify({"error": "找不到上傳工作。", "code": "upload_missing"}), 404
        denied = upload_session_guard(session)
        if denied: return denied
        payload = dict(session.get("payload") or {})
        mode = str(payload.get("uploadMode") or ("multipart" if session.get("r2_upload_id") else "single"))
        if mode != "multipart":
            return jsonify({"error": "single PUT 不支援跨頁續傳。", "code": "resume_not_supported"}), 409
        body = request.get_json(silent=True) or {}
        try:
            normalize_resume_identity(body, session)
        except ValueError as exc:
            return jsonify({"error": str(exc), "code": "file_identity_mismatch"}), 409
        status = str(session.get("status") or "")
        if status == "completed":
            return jsonify({
                "mode": "multipart",
                "uploadId": session["id"],
                "jobId": session["job_id"],
                "materialId": session["material_id"],
                "status": "completed",
                "parts": [],
                "uploadedParts": [],
                "missingPartNumbers": [],
            })
        if status != "uploading":
            return jsonify({"error": "此上傳工作已無法續傳。", "code": "upload_terminal", "status": status}), 409
        try:
            remote_parts = _list_r2_parts(runtime, session)
        except Exception as exc:
            return jsonify({"error": f"無法讀取 R2 multipart 狀態：{str(exc)[:240]}"}), 503
        missing = worker_protocol.missing_multipart_part_numbers(remote_parts, session["expected_parts"])
        ttl = int(_runtime_value(runtime.worker_url_ttl_seconds))
        client = runtime.r2_client_factory()
        bucket = str(_runtime_value(runtime.r2_bucket_name) or "")
        presigned = [
            {
                "partNumber": number,
                "url": client.generate_presigned_url(
                    "upload_part",
                    Params={
                        "Bucket": bucket,
                        "Key": session["staging_key"],
                        "UploadId": session["r2_upload_id"],
                        "PartNumber": number,
                    },
                    ExpiresIn=ttl,
                ),
            }
            for number in missing
        ]
        worker_repository.update_upload_session(
            upload_id,
            fields={"updated_at": _now()},
            connection_factory=runtime.connection_factory,
        )
        return jsonify({
            "mode": "multipart",
            "uploadId": session["id"],
            "jobId": session["job_id"],
            "materialId": session["material_id"],
            "status": "uploading",
            "partSize": int(session["part_size"]),
            "expectedParts": int(session["expected_parts"]),
            "parts": presigned,
            "uploadedParts": _public_r2_parts(remote_parts),
            "missingPartNumbers": missing,
            "expiresIn": ttl,
        })

    @app.post("/api/material-upload/<upload_id>/complete")
    def material_upload_complete(upload_id):
        denied = admin_guard()
        if denied: return denied
        session = _session(runtime, upload_id)
        if not session or session.get("status") != "uploading": return jsonify({"error": "上傳工作不存在或已完成。"}), 404
        denied = upload_session_guard(session)
        if denied: return denied
        body = request.get_json(silent=True) or {}; parts = body.get("parts")
        upload_mode = str((session.get("payload") or {}).get("uploadMode") or ("multipart" if session.get("r2_upload_id") else "single"))
        try:
            if upload_mode == "single":
                if not isinstance(parts, list) or len(parts) != 1 or not isinstance(parts[0], dict):
                    raise ValueError("single PUT 完成資料不完整。")
                etag = str(parts[0].get("etag") or "").strip()
                supplied_sha = str(parts[0].get("sha256") or session.get("source_sha256") or "").lower()
                if not etag:
                    raise ValueError("single PUT 缺少 ETag。")
                if not re.fullmatch(r"[a-f0-9]{64}", supplied_sha):
                    raise ValueError("single PUT 必須提供 SHA256。")
                if session.get("source_sha256") and supplied_sha != str(session.get("source_sha256") or "").lower():
                    raise ValueError("single PUT SHA256 與上傳工作不符。")
                normalized = [{"PartNumber": 1, "ETag": etag}]
                part_hashes = []
            else:
                part_hashes = worker_protocol.validate_multipart_part_sha256(
                    parts,
                    session["expected_parts"],
                    required=not bool(session.get("source_sha256")),
                )
                supplied_sha = str(session.get("source_sha256") or "").lower()
        except ValueError as exc:
            # No remote completion happened yet. Keep the upload session and
            # reservation intact so the client may resubmit corrected metadata.
            return jsonify({"error": str(exc)}), 400
        if upload_mode == "multipart":
            try:
                remote_parts = _list_r2_parts(runtime, session)
                normalized = worker_protocol.normalize_remote_multipart_parts(
                    remote_parts,
                    session["expected_parts"],
                    require_complete=True,
                )
                normalized = [
                    {"PartNumber": part["PartNumber"], "ETag": part["ETag"]}
                    for part in normalized
                ]
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            except Exception as exc:
                return jsonify({"error": f"無法讀取 R2 multipart 狀態：{str(exc)[:240]}"}), 503
        try:
            if upload_mode == "multipart":
                runtime.r2_client_factory().complete_multipart_upload(Bucket=str(_runtime_value(runtime.r2_bucket_name) or ""), Key=session["staging_key"], UploadId=session["r2_upload_id"], MultipartUpload={"Parts": normalized})
            head = runtime.r2_client_factory().head_object(Bucket=str(_runtime_value(runtime.r2_bucket_name) or ""), Key=session["staging_key"])
            if int(head.get("ContentLength", -1)) != int(session["source_bytes"]): raise ValueError("R2 物件大小驗證失敗。")
            if upload_mode == "single":
                remote_etag = str(head.get("ETag") or "").strip().strip('"')
                expected_etag = str(normalized[0]["ETag"] or "").strip().strip('"')
                if not remote_etag or remote_etag != expected_etag:
                    raise ValueError("R2 single PUT ETag 驗證失敗。")
                record_parts = 0
                estimated_operations = 2
            else:
                remote_metadata = head.get("Metadata") or {}
                if session.get("source_sha256"):
                    if str(remote_metadata.get("sha256", "")).lower() != str(session["source_sha256"]).lower(): raise ValueError("R2 物件 metadata 驗證失敗。")
                elif str(remote_metadata.get("hashstrategy", "")).lower() != PART_HASH_STRATEGY:
                    raise ValueError("R2 物件完整性策略驗證失敗。")
                record_parts = len(normalized)
                estimated_operations = len(normalized) + 3
            runtime.record_r2_object(session["staging_key"], int(session["source_bytes"]), multipart_parts=record_parts, estimated_operations=estimated_operations)
            try:
                payload = dict(session.get("payload") or {})
                job_session = session
                if part_hashes:
                    payload.update({"sourcePartSha256": part_hashes, "sourcePartSize": int(session["part_size"])})
                    job_session = {**session, "payload": payload}
                elif upload_mode == "single":
                    payload.update({"sourceSha256": supplied_sha, "integrityMode": "sha256"})
                    job_session = {**session, "source_sha256": supplied_sha, "payload": payload}
                persisted_parts = (
                    [{**normalized[0], "SHA256": supplied_sha}]
                    if upload_mode == "single"
                    else normalized
                )
                created_job = worker_repository.finalize_upload_session_with_job(
                    upload_id,
                    completed_parts=persisted_parts,
                    updated_at=_now(),
                    job=_job_record_from_session(runtime, job_session),
                    connection_factory=runtime.connection_factory,
                )
                if not created_job:
                    raise ValueError("上傳工作不存在或已完成。")
                runtime.sync_media_processing_metadata(created_job, "queued")
            except Exception:
                runtime.r2_client_factory().delete_object(Bucket=str(_runtime_value(runtime.r2_bucket_name) or ""), Key=session["staging_key"])
                runtime.record_r2_deleted(session["staging_key"])
                raise
            runtime.release_reservation(upload_id, "completed")
        except Exception as exc:
            _fail_upload(runtime, session, "validation_failed", delete_object=True)
            return jsonify({"error": f"直傳完成驗證失敗：{str(exc)[:300]}"}), 400
        return jsonify({"accepted": True, "jobId": session["job_id"], "status": "queued"}), 202

    @app.post("/api/material-upload/<upload_id>/abort")
    def material_upload_abort(upload_id):
        denied = admin_guard()
        if denied: return denied
        session = _session(runtime, upload_id)
        if not session: return jsonify({"error": "找不到上傳工作。"}), 404
        denied = upload_session_guard(session)
        if denied: return denied
        if session.get("status") == "uploading":
            if session.get("r2_upload_id"):
                try: runtime.r2_client_factory().abort_multipart_upload(Bucket=str(_runtime_value(runtime.r2_bucket_name) or ""), Key=session["staging_key"], UploadId=session["r2_upload_id"])
                except Exception: pass
            else:
                try:
                    runtime.r2_client_factory().delete_object(Bucket=str(_runtime_value(runtime.r2_bucket_name) or ""), Key=session["staging_key"])
                    runtime.record_r2_deleted(session["staging_key"])
                except Exception:
                    pass
            worker_repository.cas_upload_session_status(
                upload_id,
                expected_status="uploading",
                new_status="aborted",
                updated_at=_now(),
                connection_factory=runtime.connection_factory,
            )
            runtime.release_reservation(upload_id, "aborted")
        return jsonify({"ok": True})

    app.extensions["teacher_free_worker_67_registered"] = True
    return app


__all__ = ["WorkerWebRuntime", "register_free_worker"]
