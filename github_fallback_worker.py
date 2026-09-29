"""Ephemeral GitHub Actions fallback for material jobs.

The normal Windows Worker remains primary. This runner reuses the same durable
Web queue/protocol, processes only a bounded number of already queued jobs, and
then exits. It never receives a production database credential.
"""
from __future__ import annotations

import os
import sys

import material_worker as worker
from teacher_app.worker.media_transcode_compat import install


install(worker)


def _max_jobs() -> int:
    try:
        value = int(os.environ.get("MATERIAL_FALLBACK_MAX_JOBS", "3") or 3)
    except (TypeError, ValueError):
        value = 3
    return max(1, min(10, value))


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
