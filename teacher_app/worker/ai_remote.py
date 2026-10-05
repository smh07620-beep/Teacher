"""HTTPS control plane for the dedicated hospital AI Worker.

The trusted Worker never needs a production PostgreSQL login in HTTPS mode.
Only small JSON control/state messages pass through Render; source/artifact bytes
continue to move directly between the Worker and the configured durable storage.
"""
from __future__ import annotations

import hmac
import os
import threading
import time
import uuid
from collections import OrderedDict
from typing import Any
from urllib.parse import urlparse

import requests


TRANSPORT_HTTPS = "https"
TRANSPORT_DATABASE = "database"
_RPC_RECEIPT_TTL_SECONDS = 300.0
_RPC_RECEIPT_MAX = 512
_RPC_LOCK = threading.Lock()
_RPC_CALL_LOCKS: dict[str, threading.Lock] = {}
_RPC_RECEIPTS: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()


def _env_int(name: str, default: int, lower: int, upper: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)) or default)
    except (TypeError, ValueError):
        value = default
    return max(lower, min(upper, value))


def _worker_token() -> str:
    return str(
        os.environ.get("AI_WORKER_TOKEN")
        or os.environ.get("MATERIAL_WORKER_TOKEN")
        or ""
    ).strip()


def transport_mode() -> str:
    """Resolve AI Worker control transport without probing PostgreSQL."""
    configured = str(os.environ.get("AI_WORKER_TRANSPORT") or "auto").strip().lower()
    if configured in {"https", "web", "http"}:
        return TRANSPORT_HTTPS
    if configured in {"database", "db", "postgres", "postgresql"}:
        return TRANSPORT_DATABASE
    if configured not in {"", "auto"}:
        raise RuntimeError("AI_WORKER_TRANSPORT 必須是 auto、https 或 database。")
    base_url = str(os.environ.get("TEACHER_BASE_URL") or "").strip()
    return TRANSPORT_HTTPS if base_url and _worker_token() else TRANSPORT_DATABASE


def web_transport_enabled() -> bool:
    return transport_mode() == TRANSPORT_HTTPS


def _validate_base_url(value: str) -> str:
    base = str(value or "").strip().rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme == "https" and parsed.hostname:
        return base
    allow_local = str(os.environ.get("AI_WORKER_ALLOW_INSECURE_LOCAL_HTTP") or "").strip().lower() in {
        "1", "true", "yes", "on"
    }
    if (
        allow_local
        and parsed.scheme == "http"
        and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    ):
        return base
    raise RuntimeError("TEACHER_BASE_URL 必須是 HTTPS URL；本機測試例外需明確啟用。")


class AIWorkerApi:
    """Small authenticated JSON client used by the hospital AI Worker."""

    def __init__(self, *, worker_id: str):
        self.worker_id = str(worker_id or "").strip()[:100]
        self.base_url = _validate_base_url(os.environ.get("TEACHER_BASE_URL", ""))
        self.token = _worker_token()
        if not self.worker_id:
            raise RuntimeError("AI Worker ID 尚未設定。")
        if not self.token:
            raise RuntimeError("AI_WORKER_TOKEN / MATERIAL_WORKER_TOKEN 尚未設定。")
        self.timeout_seconds = _env_int("AI_WORKER_HTTP_TIMEOUT_SECONDS", 20, 5, 90)
        self.attempts = _env_int("AI_WORKER_HTTP_ATTEMPTS", 3, 1, 6)
        self.job_heartbeat_seconds = _env_int("AI_WORKER_JOB_HEARTBEAT_SECONDS", 30, 10, 90)
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": "Bearer " + self.token,
            "Accept": "application/json",
        })
        self._active_lock = threading.Lock()
        self._active_jobs: dict[tuple[str, str, str], threading.Event] = {}

    def _post(self, path: str, payload: dict, *, call_id: str = "") -> dict:
        last_error: Exception | None = None
        for attempt in range(1, self.attempts + 1):
            try:
                response = self.session.post(
                    self.base_url + path,
                    json=payload,
                    timeout=self.timeout_seconds,
                )
                data = response.json() if response.content else {}
                if response.status_code >= 300:
                    message = str((data or {}).get("error") or f"HTTP {response.status_code}")[:300]
                    if response.status_code in {400, 401, 403, 404, 409, 413}:
                        raise RuntimeError(message)
                    raise requests.HTTPError(message, response=response)
                return data if isinstance(data, dict) else {}
            except RuntimeError:
                raise
            except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
                last_error = exc
                if attempt >= self.attempts:
                    break
                time.sleep(min(2.0, 0.35 * (2 ** (attempt - 1))))
        raise RuntimeError(
            "AI Worker HTTPS control plane 暫時無法連線。"
        ) from last_error

    def heartbeat(self, capabilities: dict) -> dict:
        return self._post(
            "/api/ai-worker/heartbeat",
            {"workerId": self.worker_id, "capabilities": dict(capabilities or {})},
        )

    def _rpc(self, op: str, args: tuple, kwargs: dict, *, call_id: str) -> Any:
        data = self._post(
            "/api/ai-worker/rpc",
            {
                "workerId": self.worker_id,
                "callId": call_id,
                "op": str(op or "")[:120],
                "args": list(args),
                "kwargs": dict(kwargs),
            },
            call_id=call_id,
        )
        return data.get("result")

    @staticmethod
    def _queue_from_op(op: str) -> str:
        parts = str(op or "").split(".")
        if len(parts) == 3 and parts[0] == "queue":
            return parts[1]
        return ""

    def _start_job_heartbeat(self, queue: str, job: dict) -> None:
        job_id = str((job or {}).get("id") or "")
        token = str((job or {}).get("claimToken") or "")
        if not queue or not job_id or not token:
            return
        key = (queue, job_id, token)
        stop = threading.Event()
        with self._active_lock:
            previous = self._active_jobs.get(key)
            if previous is not None:
                return
            self._active_jobs[key] = stop

        def run() -> None:
            while not stop.wait(self.job_heartbeat_seconds):
                try:
                    self._rpc(
                        "queue.touch",
                        (queue, job_id, token),
                        {},
                        call_id=uuid.uuid4().hex,
                    )
                except Exception:
                    # The normal 30s worker heartbeat remains the health signal.
                    # A transient per-job touch failure must not kill local media
                    # rendering; the next touch/progress update can recover it.
                    continue

        threading.Thread(
            target=run,
            name=f"teacher-ai-job-heartbeat-{queue}",
            daemon=True,
        ).start()

    def _stop_job_heartbeat(self, queue: str, job_id: str, token: str) -> None:
        key = (str(queue or ""), str(job_id or ""), str(token or ""))
        with self._active_lock:
            stop = self._active_jobs.pop(key, None)
        if stop is not None:
            stop.set()

    def call(self, op: str, *args, **kwargs):
        call_id = uuid.uuid4().hex
        result = self._rpc(op, args, kwargs, call_id=call_id)
        queue = self._queue_from_op(op)
        action = str(op or "").split(".")[-1]
        if queue and action in {"claim", "claim_job"} and isinstance(result, dict):
            self._start_job_heartbeat(queue, result)
        elif queue and action in {"complete", "complete_job", "fail", "fail_job"} and len(args) >= 2:
            if result:
                self._stop_job_heartbeat(queue, str(args[0]), str(args[1]))
        return result

    def close(self) -> None:
        with self._active_lock:
            stops = list(self._active_jobs.values())
            self._active_jobs.clear()
        for stop in stops:
            stop.set()
        self.session.close()


def _queue_adapter(queue: str):
    from teacher_app.assessments import ai_job_repository
    from teacher_app.materials import (
        ai_presentation_repository,
        ai_video_repository,
        media_audio_repository,
        media_script_repository,
        media_subtitle_repository,
    )

    if queue == "ai_questions":
        return {
            "repo": ai_job_repository,
            "get": ai_job_repository.get_job,
            "claim": ai_job_repository.claim,
            "progress": ai_job_repository.set_progress,
            "complete": ai_job_repository.complete,
            "fail": ai_job_repository.fail,
            "list_queued": ai_job_repository.list_queued,
            "recover": ai_job_repository.requeue_stale_processing,
        }
    if queue == "media_scripts":
        return {
            "repo": media_script_repository,
            "get": media_script_repository.get_job,
            "claim": media_script_repository.claim,
            "progress": media_script_repository.set_progress,
            "complete": media_script_repository.complete,
            "fail": media_script_repository.fail,
            "list_queued": media_script_repository.list_queued,
            "recover": media_script_repository.requeue_stale_processing,
        }
    if queue == "ai_presentations":
        return {
            "repo": ai_presentation_repository,
            "get": ai_presentation_repository.get_job,
            "claim": ai_presentation_repository.claim_job,
            "progress": ai_presentation_repository.set_job_progress,
            "complete": ai_presentation_repository.complete_job,
            "fail": ai_presentation_repository.fail_job,
            "list_queued": ai_presentation_repository.list_queued,
            "recover": ai_presentation_repository.requeue_stale_processing,
        }
    if queue == "ai_videos":
        return {
            "repo": ai_video_repository,
            "get": ai_video_repository.get_job,
            "claim": ai_video_repository.claim,
            "progress": ai_video_repository.set_progress,
            "complete": ai_video_repository.complete,
            "fail": ai_video_repository.fail,
            "list_queued": ai_video_repository.list_queued,
            "recover": ai_video_repository.requeue_stale_processing,
        }
    if queue == "media_audio":
        return {
            "repo": media_audio_repository,
            "get": media_audio_repository.get_job,
            "claim": media_audio_repository.claim,
            "progress": media_audio_repository.set_progress,
            "complete": media_audio_repository.complete,
            "fail": media_audio_repository.fail,
            "list_queued": media_audio_repository.list_queued,
            "recover": media_audio_repository.requeue_stale_processing,
        }
    if queue == "media_subtitles":
        return {
            "repo": media_subtitle_repository,
            "get": media_subtitle_repository.get_job,
            "claim": media_subtitle_repository.claim,
            "progress": media_subtitle_repository.set_progress,
            "complete": media_subtitle_repository.complete,
            "fail": media_subtitle_repository.fail,
            "list_queued": media_subtitle_repository.list_queued,
            "recover": media_subtitle_repository.requeue_stale_processing,
        }
    raise ValueError("不支援的 AI Worker queue。")


def _same_claim(job: dict | None, token: str, status: str) -> bool:
    return bool(
        job
        and str(job.get("status") or "") == status
        and hmac.compare_digest(str(job.get("claimToken") or ""), str(token or ""))
    )


def _execute_queue(queue: str, action: str, args: list, kwargs: dict):
    adapter = _queue_adapter(queue)
    if action == "list_queued":
        return adapter["list_queued"](*args, **kwargs)
    if action == "requeue_stale_processing":
        return adapter["recover"](*args, **kwargs)
    if action in {"claim", "claim_job"}:
        if len(args) < 2:
            raise ValueError("AI queue claim 參數不足。")
        job_id, token = str(args[0] or ""), str(args[1] or "")
        claimed = adapter["claim"](job_id, token)
        if claimed:
            return claimed
        existing = adapter["get"](job_id)
        return existing if _same_claim(existing, token, "processing") else None
    if action in {"set_progress", "set_job_progress"}:
        return adapter["progress"](*args, **kwargs)
    if action in {"complete", "complete_job"}:
        if len(args) < 2:
            raise ValueError("AI queue complete 參數不足。")
        ok = adapter["complete"](*args, **kwargs)
        if ok:
            return True
        return _same_claim(adapter["get"](str(args[0] or "")), str(args[1] or ""), "completed")
    if action in {"fail", "fail_job"}:
        if len(args) < 2:
            raise ValueError("AI queue fail 參數不足。")
        ok = adapter["fail"](*args, **kwargs)
        if ok:
            return True
        return _same_claim(adapter["get"](str(args[0] or "")), str(args[1] or ""), "failed")
    raise ValueError("不支援的 AI queue 操作。")


def _touch_queue(queue: str, job_id: str, token: str) -> bool:
    adapter = _queue_adapter(queue)
    job = adapter["get"](str(job_id or ""))
    if not _same_claim(job, token, "processing"):
        return False
    return bool(adapter["progress"](
        str(job_id or ""),
        str(token or ""),
        float(job.get("progressPercent") or 0),
        str(job.get("progressStage") or "AI Worker 處理中"),
        str(job.get("progressDetail") or "AI Worker 工作 heartbeat"),
    ))


def _nonqueue_operation(op: str):
    from teacher_app.assessments import repository as assessment_repository
    from teacher_app.materials import (
        ai_presentation_repository,
        ai_video_repository,
        external_media,
        media_script_repository,
        media_subtitle_repository,
        repository as material_repository,
    )
    from teacher_app.storage import r2_budget, r2_ledger

    operations = {
        "assessment.list_questions": assessment_repository.list_questions,
        "material.get_material": material_repository.get_material,
        "material.insert_material": material_repository.insert_material,
        "media_script.get_script": media_script_repository.get_script,
        "presentation.get_template": ai_presentation_repository.get_template,
        "presentation.get_presentation": ai_presentation_repository.get_presentation,
        "presentation.get_presentation_by_source_job_id": ai_presentation_repository.get_presentation_by_source_job_id,
        "presentation.create_presentation": ai_presentation_repository.create_presentation,
        "presentation.update_presentation_artifact": ai_presentation_repository.update_presentation_artifact,
        "presentation.update_presentation_quality": ai_presentation_repository.update_presentation_quality,
        "video.get_video_by_source_job": ai_video_repository.get_video_by_source_job,
        "video.create_video": ai_video_repository.create_video,
        "subtitle.create_subtitle": media_subtitle_repository.create_subtitle,
        "external_media.get_external_media": external_media.get_external_media,
        "r2.reserve_upload": r2_budget.reserve_upload,
        "r2.release_reservation": r2_budget.release_reservation,
        "r2.record_object": r2_ledger.record_object,
    }
    return operations.get(op)


def execute_rpc_operation(op: str, args: list | tuple | None, kwargs: dict | None):
    """Execute exactly one allow-listed server-side repository operation."""
    name = str(op or "").strip()
    positional = list(args or [])
    keyword = dict(kwargs or {})
    if name == "queue.touch":
        if len(positional) != 3:
            raise ValueError("AI queue heartbeat 參數不足。")
        return _touch_queue(str(positional[0]), str(positional[1]), str(positional[2]))
    parts = name.split(".")
    if len(parts) == 3 and parts[0] == "queue":
        return _execute_queue(parts[1], parts[2], positional, keyword)

    target = _nonqueue_operation(name)
    if target is None:
        raise ValueError("AI Worker RPC 操作不在允許清單。")

    # Job-derived artifact rows use the job id as their idempotency boundary.
    if name == "presentation.create_presentation":
        source_job_id = str(keyword.get("source_job_id") or "")
        if source_job_id:
            from teacher_app.materials import ai_presentation_repository
            existing = ai_presentation_repository.get_presentation_by_source_job_id(source_job_id)
            if existing:
                return existing
    elif name == "video.create_video":
        source_job_id = str(keyword.get("source_job_id") or "")
        if source_job_id:
            from teacher_app.materials import ai_video_repository
            existing = ai_video_repository.get_video_by_source_job(source_job_id)
            if existing:
                return existing
    elif name == "subtitle.create_subtitle":
        source_job_id = str(keyword.get("source_job_id") or "")
        if source_job_id:
            from teacher_app.materials import media_subtitle_repository
            existing = media_subtitle_repository.get_subtitle_by_source_job_id(source_job_id)
            if existing:
                return existing

    return target(*positional, **keyword)


def execute_rpc_call(call_id: str, op: str, args: list | tuple | None, kwargs: dict | None):
    """Short-lived replay protection for HTTP response loss/retry."""
    key = str(call_id or "").strip()
    if not key or len(key) > 80:
        raise ValueError("AI Worker callId 不合法。")
    with _RPC_LOCK:
        call_lock = _RPC_CALL_LOCKS.setdefault(key, threading.Lock())
    with call_lock:
        now = time.monotonic()
        with _RPC_LOCK:
            stale = [item for item, (stamp, _value) in _RPC_RECEIPTS.items() if now - stamp > _RPC_RECEIPT_TTL_SECONDS]
            for item in stale:
                _RPC_RECEIPTS.pop(item, None)
                _RPC_CALL_LOCKS.pop(item, None)
            cached = _RPC_RECEIPTS.get(key)
            if cached is not None:
                _RPC_RECEIPTS.move_to_end(key)
                return cached[1], True

        result = execute_rpc_operation(op, args, kwargs)
        with _RPC_LOCK:
            _RPC_RECEIPTS[key] = (now, result)
            _RPC_RECEIPTS.move_to_end(key)
            while len(_RPC_RECEIPTS) > _RPC_RECEIPT_MAX:
                old_key, _old = _RPC_RECEIPTS.popitem(last=False)
                _RPC_CALL_LOCKS.pop(old_key, None)
        return result, False


def _proxy(api: AIWorkerApi, op: str):
    def call(*args, **kwargs):
        return api.call(op, *args, **kwargs)
    call.__name__ = "remote_" + op.replace(".", "_")
    return call


def install_remote_repository_proxies(api: AIWorkerApi) -> None:
    """Replace only Worker-used persistence seams with HTTPS RPC proxies."""
    from teacher_app.assessments import ai_job_repository, repository as assessment_repository
    from teacher_app.materials import (
        ai_presentation_repository,
        ai_video_repository,
        external_media,
        media_audio_repository,
        media_script_repository,
        media_subtitle_repository,
        repository as material_repository,
    )
    from teacher_app.storage import r2_budget, r2_ledger

    bindings = (
        (ai_job_repository, "list_queued", "queue.ai_questions.list_queued"),
        (ai_job_repository, "claim", "queue.ai_questions.claim"),
        (ai_job_repository, "set_progress", "queue.ai_questions.set_progress"),
        (ai_job_repository, "complete", "queue.ai_questions.complete"),
        (ai_job_repository, "fail", "queue.ai_questions.fail"),
        (ai_job_repository, "requeue_stale_processing", "queue.ai_questions.requeue_stale_processing"),

        (media_script_repository, "list_queued", "queue.media_scripts.list_queued"),
        (media_script_repository, "claim", "queue.media_scripts.claim"),
        (media_script_repository, "set_progress", "queue.media_scripts.set_progress"),
        (media_script_repository, "complete", "queue.media_scripts.complete"),
        (media_script_repository, "fail", "queue.media_scripts.fail"),
        (media_script_repository, "requeue_stale_processing", "queue.media_scripts.requeue_stale_processing"),

        (ai_presentation_repository, "list_queued", "queue.ai_presentations.list_queued"),
        (ai_presentation_repository, "claim_job", "queue.ai_presentations.claim_job"),
        (ai_presentation_repository, "set_job_progress", "queue.ai_presentations.set_job_progress"),
        (ai_presentation_repository, "complete_job", "queue.ai_presentations.complete_job"),
        (ai_presentation_repository, "fail_job", "queue.ai_presentations.fail_job"),
        (ai_presentation_repository, "requeue_stale_processing", "queue.ai_presentations.requeue_stale_processing"),

        (ai_video_repository, "list_queued", "queue.ai_videos.list_queued"),
        (ai_video_repository, "claim", "queue.ai_videos.claim"),
        (ai_video_repository, "set_progress", "queue.ai_videos.set_progress"),
        (ai_video_repository, "complete", "queue.ai_videos.complete"),
        (ai_video_repository, "fail", "queue.ai_videos.fail"),
        (ai_video_repository, "requeue_stale_processing", "queue.ai_videos.requeue_stale_processing"),

        (media_audio_repository, "list_queued", "queue.media_audio.list_queued"),
        (media_audio_repository, "claim", "queue.media_audio.claim"),
        (media_audio_repository, "set_progress", "queue.media_audio.set_progress"),
        (media_audio_repository, "complete", "queue.media_audio.complete"),
        (media_audio_repository, "fail", "queue.media_audio.fail"),
        (media_audio_repository, "requeue_stale_processing", "queue.media_audio.requeue_stale_processing"),

        (media_subtitle_repository, "list_queued", "queue.media_subtitles.list_queued"),
        (media_subtitle_repository, "claim", "queue.media_subtitles.claim"),
        (media_subtitle_repository, "set_progress", "queue.media_subtitles.set_progress"),
        (media_subtitle_repository, "complete", "queue.media_subtitles.complete"),
        (media_subtitle_repository, "fail", "queue.media_subtitles.fail"),
        (media_subtitle_repository, "requeue_stale_processing", "queue.media_subtitles.requeue_stale_processing"),

        (assessment_repository, "list_questions", "assessment.list_questions"),
        (material_repository, "get_material", "material.get_material"),
        (material_repository, "insert_material", "material.insert_material"),
        (media_script_repository, "get_script", "media_script.get_script"),
        (ai_presentation_repository, "get_template", "presentation.get_template"),
        (ai_presentation_repository, "get_presentation", "presentation.get_presentation"),
        (ai_presentation_repository, "get_presentation_by_source_job_id", "presentation.get_presentation_by_source_job_id"),
        (ai_presentation_repository, "create_presentation", "presentation.create_presentation"),
        (ai_presentation_repository, "update_presentation_artifact", "presentation.update_presentation_artifact"),
        (ai_presentation_repository, "update_presentation_quality", "presentation.update_presentation_quality"),
        (ai_video_repository, "get_video_by_source_job", "video.get_video_by_source_job"),
        (ai_video_repository, "create_video", "video.create_video"),
        (media_subtitle_repository, "create_subtitle", "subtitle.create_subtitle"),
        (external_media, "get_external_media", "external_media.get_external_media"),
        (r2_budget, "reserve_upload", "r2.reserve_upload"),
        (r2_budget, "release_reservation", "r2.release_reservation"),
        (r2_ledger, "record_object", "r2.record_object"),
    )
    for module, attribute, operation in bindings:
        setattr(module, attribute, _proxy(api, operation))


__all__ = [
    "AIWorkerApi",
    "TRANSPORT_DATABASE",
    "TRANSPORT_HTTPS",
    "execute_rpc_call",
    "execute_rpc_operation",
    "install_remote_repository_proxies",
    "transport_mode",
    "web_transport_enabled",
]
