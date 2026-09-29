"""Ephemeral GitHub Actions fallback for material jobs.

The normal Windows Worker remains primary. This runner reuses the same durable
Web queue/protocol, waits through a local-Worker grace period, processes only a
bounded number of still-queued jobs, and then exits. It never receives a
production database credential.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import material_worker as worker
from teacher_app.worker.media_transcode_compat import install


install(worker)


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)) or default)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _max_jobs() -> int:
    return _bounded_int("MATERIAL_FALLBACK_MAX_JOBS", 3, 1, 10)


def _grace_seconds() -> int:
    return _bounded_int("MATERIAL_FALLBACK_GRACE_SECONDS", 300, 0, 900)


def main() -> int:
    try:
        api = worker.WorkerApi()
    except RuntimeError as exc:
        worker.log(f"fallback configuration unavailable: {exc}")
        return 2

    caps = worker.capability()
    required = {
        "ffmpeg": bool((caps.get("ffmpeg") or {}).get("available")),
        "ffprobe": bool((caps.get("ffprobe") or {}).get("available")),
        "libreOffice": bool((caps.get("libreOffice") or {}).get("available")),
    }
    worker.log(
        "fallback startup "
        + " ".join(f"{name}={str(ready).lower()}" for name, ready in required.items())
    )
    if not all(required.values()):
        worker.log("fallback runtime missing LibreOffice/FFmpeg capability; refusing to claim jobs")
        return 3

    grace = _grace_seconds()
    if grace:
        worker.log(f"fallback grace period {grace}s; local Worker keeps first chance")
        time.sleep(grace)

    processed = 0
    for _ in range(_max_jobs()):
        try:
            api.heartbeat(capabilities=caps)
            data = api.post(
                "/api/material-worker/claim",
                {
                    "workerId": worker.WORKER_ID,
                    "capabilities": caps,
                    **worker.AUTO_UPDATER.metadata(),
                },
            )
        except Exception as exc:
            worker.log(f"fallback claim unavailable: {str(exc)[:400]}")
            return 4

        job = data.get("job") if isinstance(data, dict) else None
        if not job:
            worker.log(f"fallback queue empty after {processed} job(s); exiting")
            return 0

        worker.process_one(api, job, capabilities=caps)
        processed += 1

    worker.log(f"fallback bounded run completed {processed} job(s); exiting")
    return 0


if __name__ == "__main__":
    sys.exit(main())
