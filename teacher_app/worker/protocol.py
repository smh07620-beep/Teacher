"""Pure protocol rules for Teacher's single local material worker."""
from __future__ import annotations

import datetime as dt
import hmac
import re
from typing import Any, Callable, Mapping, Sequence

from teacher_app.worker import repository


CLIENT_FINGERPRINT_STRATEGY = "sha256-part-tree-v1"


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


def validate_multipart_part_sha256(
    parts: Any,
    expected_parts: Any,
    *,
    required: bool = False,
) -> list[str]:
    """Validate optional per-part SHA-256 digests carried by browser uploads."""

    try:
        expected_count = int(expected_parts)
    except (TypeError, ValueError) as exc:
        raise ValueError("multipart expected_parts 不合法。") from exc
    if expected_count < 1 or not isinstance(parts, list) or len(parts) != expected_count:
        raise ValueError("multipart parts 不完整。")
    values: list[str] = []
    for expected, part in enumerate(parts, 1):
        if not isinstance(part, Mapping):
            raise ValueError("multipart part 格式錯誤。")
        try:
            number = int(part.get("partNumber", 0) or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("multipart part 格式錯誤。") from exc
        if number != expected:
            raise ValueError("multipart part 格式錯誤。")
        values.append(str(part.get("sha256") or "").lower())
    present = [bool(value) for value in values]
    if any(present) and not all(present):
        raise ValueError("multipart 分段 SHA256 不完整。")
    if required and not all(present):
        raise ValueError("multipart 必須提供每段 SHA256。")
    if not any(present):
        return []
    if any(not re.fullmatch(r"[a-f0-9]{64}", value) for value in values):
        raise ValueError("multipart 分段 SHA256 格式錯誤。")
    return values


def normalize_remote_multipart_parts(
    parts: Any,
    expected_parts: Any,
    *,
    require_complete: bool = False,
) -> list[dict[str, Any]]:
    """Normalize R2 ``list_parts`` rows without trusting a browser manifest."""

    try:
        expected_count = int(expected_parts)
    except (TypeError, ValueError) as exc:
        raise ValueError("multipart expected_parts 不合法。") from exc
    if expected_count < 1:
        raise ValueError("multipart expected_parts 不合法。")
    if not isinstance(parts, list):
        raise ValueError("R2 multipart parts 格式錯誤。")
    normalized: list[dict[str, Any]] = []
    seen: set[int] = set()
    for part in parts:
        if not isinstance(part, Mapping):
            raise ValueError("R2 multipart part 格式錯誤。")
        try:
            number = int(part.get("PartNumber", 0) or 0)
            size = int(part.get("Size", 0) or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("R2 multipart part 格式錯誤。") from exc
        etag = str(part.get("ETag") or "").strip()
        if number < 1 or number > expected_count or number in seen or not etag:
            raise ValueError("R2 multipart part 格式錯誤。")
        seen.add(number)
        normalized.append({"PartNumber": number, "ETag": etag, "Size": max(0, size)})
    normalized.sort(key=lambda item: item["PartNumber"])
    if require_complete and [item["PartNumber"] for item in normalized] != list(range(1, expected_count + 1)):
        raise ValueError("R2 multipart parts 尚未完整上傳。")
    return normalized


def missing_multipart_part_numbers(parts: Sequence[Mapping[str, Any]], expected_parts: Any) -> list[int]:
    """Return missing part numbers from server-authoritative R2 list-parts state."""

    try:
        expected_count = int(expected_parts)
    except (TypeError, ValueError) as exc:
        raise ValueError("multipart expected_parts 不合法。") from exc
    if expected_count < 1:
        raise ValueError("multipart expected_parts 不合法。")
    present = {int(part.get("PartNumber", 0) or 0) for part in parts if isinstance(part, Mapping)}
    return [number for number in range(1, expected_count + 1) if number not in present]


def normalize_client_file_identity(
    *,
    filename: Any,
    size: Any,
    last_modified: Any,
    fingerprint: Any,
    strategy: Any,
    part_size: Any,
    required: bool = False,
) -> dict[str, Any]:
    """Validate the browser-computed identity used to bind resumable uploads."""

    fingerprint_value = str(fingerprint or "").strip().lower()
    strategy_value = str(strategy or "").strip().lower()
    if not fingerprint_value and not strategy_value and last_modified in (None, "") and part_size in (None, ""):
        if required:
            raise ValueError("缺少可續傳檔案識別資訊。")
        return {}
    if strategy_value != CLIENT_FINGERPRINT_STRATEGY:
        raise ValueError("不支援的續傳檔案指紋策略。")
    if not re.fullmatch(r"[a-f0-9]{64}", fingerprint_value):
        raise ValueError("續傳檔案指紋格式錯誤。")
    try:
        size_value = int(size)
        modified_value = int(last_modified)
        part_size_value = int(part_size)
    except (TypeError, ValueError) as exc:
        raise ValueError("續傳檔案識別資訊格式錯誤。") from exc
    name_value = str(filename or "").strip()
    if not name_value or size_value <= 0 or modified_value < 0 or part_size_value <= 0:
        raise ValueError("續傳檔案識別資訊格式錯誤。")
    return {
        "filename": name_value,
        "size": size_value,
        "lastModified": modified_value,
        "fingerprint": fingerprint_value,
        "strategy": strategy_value,
        "partSize": part_size_value,
    }


def client_file_identity_matches(stored: Any, supplied: Any) -> bool:
    """Constant-time fingerprint comparison plus exact browser file metadata."""

    if not isinstance(stored, Mapping) or not isinstance(supplied, Mapping):
        return False
    for key in ("filename", "size", "lastModified", "strategy", "partSize"):
        if str(stored.get(key, "")) != str(supplied.get(key, "")):
            return False
    stored_fingerprint = str(stored.get("fingerprint") or "")
    supplied_fingerprint = str(supplied.get("fingerprint") or "")
    return bool(stored_fingerprint) and hmac.compare_digest(stored_fingerprint, supplied_fingerprint)


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
