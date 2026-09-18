"""Pure protocol rules for Teacher's single local material worker."""
from __future__ import annotations

import datetime as dt
import hmac
import re
from typing import Any, Callable, Mapping, Sequence

from teacher_app.worker import repository


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize_worker_id(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9._:-]", "", str(value or ""))[:160]


def bearer_token_matches(configured_token: Any, authorization_header: Any) -> bool:
    """Constant-time validation for the one local worker bearer token."""
    token = str(configured_token or "")
    supplied = str(authorization_header or "")
    if not token:
        return False
    return hmac.compare_digest(supplied, f"Bearer {token}")


def sanitize_metadata(body: Any) -> dict[str, Any]:
    """Whitelist bounded, non-secret worker build metadata."""
    body = body if isinstance(body, dict) else {}
    version = re.sub(
        r"[^0-9A-Za-z._-]",
        "",
        str(body.get("workerVersion") or ""),
    )[:32]
    sha = str(body.get("workerSha") or "").lower()
    sha = sha if re.fullmatch(r"[0-9a-f]{7,40}", sha) else ""
    branch = re.sub(
        r"[^0-9A-Za-z._/-]",
        "",
        str(body.get("workerBranch") or ""),
    )[:80]
    checked = str(body.get("lastUpdateCheckAt") or "")[:64]
    try:
        if checked:
            dt.datetime.fromisoformat(checked.replace("Z", "+00:00"))
    except ValueError:
        checked = ""
    return {
        "workerVersion": version,
        "workerSha": sha,
        "workerBranch": branch,
        "updateAvailable": bool(body.get("updateAvailable", False)),
        "lastUpdateCheckAt": checked,
    }


def heartbeat_capabilities(
    capabilities: Any,
    metadata: Any = None,
) -> dict[str, Any]:
    payload = dict(capabilities) if isinstance(capabilities, Mapping) else {}
    payload.update(sanitize_metadata(metadata))
    return payload


def retry_plan(
    attempts: Any,
    max_attempts: Any,
    *,
    stamp: str | None = None,
) -> dict[str, Any]:
    """Return the legacy retry/backoff decision without touching persistence."""
    try:
        attempt_count = max(0, int(attempts or 0))
    except (TypeError, ValueError):
        attempt_count = 0
    try:
        maximum = max(1, int(max_attempts or 1))
    except (TypeError, ValueError):
        maximum = 1
    if attempt_count >= maximum:
        return {"retry": False, "delaySeconds": 0, "availableAt": ""}
    delay = min(300, max(10, attempt_count * 15))
    if stamp:
        current = dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        if current.tzinfo is None:
            current = current.replace(tzinfo=dt.timezone.utc)
    else:
        current = dt.datetime.now(dt.timezone.utc)
    return {
        "retry": True,
        "delaySeconds": delay,
        "availableAt": (current + dt.timedelta(seconds=delay)).isoformat(),
    }


def validate_multipart_parts(
    parts: Any,
    expected_parts: Any,
) -> list[dict[str, Any]]:
    """Validate the ordered multipart completion manifest.

    Raises ``ValueError`` for malformed input so the HTTP adapter can preserve
    its existing 400 response without owning multipart protocol rules.
    """
    try:
        expected_count = int(expected_parts)
    except (TypeError, ValueError) as exc:
        raise ValueError("multipart expected_parts 不合法。") from exc
    if expected_count < 1:
        raise ValueError("multipart expected_parts 不合法。")
    if not isinstance(parts, list) or len(parts) != expected_count:
        raise ValueError("multipart parts 不完整。")
    normalized: list[dict[str, Any]] = []
    for expected, part in enumerate(parts, 1):
        if not isinstance(part, Mapping):
            raise ValueError("multipart part 格式錯誤。")
        try:
            number = int(part.get("partNumber", 0) or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("multipart part 格式錯誤。") from exc
        etag = str(part.get("etag") or "")
        if number != expected or not etag.strip():
            raise ValueError("multipart part 格式錯誤。")
        normalized.append({"PartNumber": expected, "ETag": etag})
    return normalized


def record_heartbeat(
    worker_id: str,
    *,
    capabilities: Any = None,
    current_job_id: str = "",
    metadata: Any = None,
    stamp: str | None = None,
    touch_job: Callable[[str, str], None] | None = None,
    connection_factory: repository.ConnectionFactory | None = None,
) -> str:
    """Persist heartbeat state and optionally touch the current legacy job row."""
    seen = stamp or now()
    repository.upsert_heartbeat(
        worker_id,
        last_seen=seen,
        capabilities=heartbeat_capabilities(capabilities, metadata),
        current_job_id=current_job_id,
        connection_factory=connection_factory,
    )
    if current_job_id and touch_job is not None:
        touch_job(current_job_id, seen)
    return seen
