"""AI Worker queue orchestration for PowerPoint generation."""
from __future__ import annotations

import datetime as dt
import os
import uuid

from teacher_app.materials import ai_presentation_repository as repository
from teacher_app.materials import ai_presentation_runtime
from teacher_app.materials import ai_presentation_quality as quality


def _env_int(name: str, default: int, lower: int, upper: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)) or default)
    except (TypeError, ValueError):
        value = default
    return max(lower, min(upper, value))


def public_job(job: dict) -> dict:
    payload = {key: job.get(key) for key in (
        "id", "draftId", "templateId", "group", "area", "status", "progressPercent",
        "progressStage", "progressDetail", "result", "error", "attempts",
        "createdAt", "updatedAt", "startedAt", "completedAt",
    )}
    request_payload = dict(job.get("request") or {})
    if request_payload.get("presentationId"):
        payload["presentationId"] = str(request_payload.get("presentationId") or "")
        payload["revisionRender"] = bool(request_payload.get("renderRevision"))
    if request_payload.get("regenerate"):
        payload["regenerate"] = True
        payload["rulesetVersion"] = str(request_payload.get("rulesetVersion") or quality.RULESET_VERSION)
    payload["retryable"] = str(job.get("status") or "") == "failed" and int(job.get("attempts") or 0) < _env_int("AI_PRESENTATION_JOB_MAX_ATTEMPTS", 3, 1, 10)
    return payload


def enqueue(*, draft: dict, template_id: str, actor_username: str, slides: list[dict] | None = None) -> dict:
    return repository.create_job(
        draft_id=str(draft.get("id") or ""), template_id=str(template_id or ""),
        group_key=str(draft.get("group") or ""), training_area=str(draft.get("area") or ""),
        actor_username=actor_username, request_payload={"slides": slides} if isinstance(slides, list) else {},
    )


def enqueue_revision(*, presentation: dict, actor_username: str, idempotency_key: str = "", regenerate: bool = False) -> dict:
    """Queue a draft revision render; Web never invokes python-pptx or provider upload inline."""
    if str(presentation.get("status") or "") != "draft":
        raise ValueError("只有 draft PowerPoint revision 可以排入重新產生工作。")
    if str(presentation.get("artifactStorageKey") or ""):
        raise ValueError("此 PowerPoint revision 已經有 artifact，不需重複排入。")
    request_payload = {"presentationId": str(presentation.get("id") or ""), "renderRevision": True}
    if regenerate:
        request_payload.update({"regenerate": True, "rulesetVersion": quality.RULESET_VERSION})
    return repository.create_job(
        draft_id=str(presentation.get("draftId") or ""),
        template_id=str(presentation.get("templateId") or ""),
        group_key=str(presentation.get("group") or ""),
        training_area=str(presentation.get("area") or ""),
        actor_username=actor_username,
        request_payload=request_payload,
        idempotency_key=idempotency_key,
    )


def retry(*, job: dict) -> dict | None:
    """Reuse the existing worker protocol and idempotency key; never clone a failed job."""
    return repository.retry_failed_job(
        str(job.get("id") or ""),
        max_attempts=_env_int("AI_PRESENTATION_JOB_MAX_ATTEMPTS", 3, 1, 10),
    )


class AiPresentationJobProcessor:
    def __init__(self):
        self.stale_seconds = _env_int("AI_PRESENTATION_JOB_STALE_SECONDS", 1800, 120, 86400)

    def recover_stale(self) -> int:
        cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=self.stale_seconds)).isoformat()
        return repository.requeue_stale_processing(cutoff)

    def run_next_queued(self) -> bool:
        queued = repository.list_queued(1)
        if not queued:
            return False
        job_id, token = str(queued[0].get("id") or ""), uuid.uuid4().hex
        job = repository.claim_job(job_id, token)
        if not job:
            return False

        def progress(percent, stage, detail):
            repository.set_job_progress(job_id, token, percent, stage, detail)

        try:
            request_payload = dict(job.get("request") or {})
            if request_payload.get("renderRevision") and request_payload.get("presentationId"):
                result = ai_presentation_runtime.generate_revision(job=job, progress_callback=progress)
            else:
                result = ai_presentation_runtime.generate_presentation(job=job, progress_callback=progress)
            if not repository.complete_job(job_id, token, result):
                raise RuntimeError("PowerPoint 工作完成狀態已失效，未覆寫其他 Worker。")
        except Exception as exc:
            repository.fail_job(job_id, token, str(exc))
        return True


__all__ = ["public_job", "enqueue", "enqueue_revision", "retry", "AiPresentationJobProcessor"]
