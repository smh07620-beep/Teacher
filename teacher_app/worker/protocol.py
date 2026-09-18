"""Canonical Web-side heartbeat protocol for Teacher's single local worker."""
from __future__ import annotations

import datetime as dt
import re
from typing import Any, Callable, Mapping

from teacher_app.worker import repository


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize_worker_id(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9._:-]", "", str(value or ""))[:160]


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


def record_heartbeat(
    worker_id: str,
    *,
    capabilities: Any = None,
    current_job_id: str = "",
    metadata: Any = None,
    stamp: str | None = None,
    touch_job: Callable[[str, str], None] | None = None,
    connection_factory: Callable[[], tuple[Any, str]] | None = None,
) -> str:
    """Persist heartbeat state and optionally touch the current legacy job row.

    ``touch_job`` and ``connection_factory`` are narrow transition seams while
    material-job persistence remains legacy-owned.  The canonical worker
    protocol never imports the legacy host object directly.
    """
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
