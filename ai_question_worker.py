"""Dedicated assessment AI worker backed by the persistent DB queue."""
from __future__ import annotations

import os
import sys
import time

from teacher_app.assessments import ai_jobs
from teacher_app.assessments.question_runtime import build_canonical_question_runtime


def _env_int(name: str, default: int, lower: int, upper: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)) or default)
    except (TypeError, ValueError):
        value = default
    return max(lower, min(upper, value))


def log(message: str) -> None:
    print(f"[teacher-ai-question-worker] {message}", flush=True)


def main() -> int:
    runtime = build_canonical_question_runtime()
    processor = ai_jobs.AiQuestionJobProcessor(runtime)
    poll_seconds = _env_int("AI_QUESTION_WORKER_POLL_SECONDS", 2, 1, 30)
    recovery_seconds = _env_int("AI_QUESTION_WORKER_RECOVERY_SECONDS", 300, 30, 3600)
    next_recovery = 0.0
    log("started")
    while True:
        try:
            now = time.monotonic()
            if now >= next_recovery:
                recovered = processor.recover_stale()
                if recovered:
                    log(f"requeued stale jobs={recovered}")
                next_recovery = now + recovery_seconds
            if processor.run_next_queued():
                continue
            time.sleep(poll_seconds)
        except KeyboardInterrupt:
            log("stopped")
            return 0
        except Exception as exc:
            # Web migrations and DB/network services can come up after the worker.
            # Keep the worker alive and retry without claiming a job twice.
            log(f"loop error: {str(exc)[:800]}")
            time.sleep(poll_seconds)


if __name__ == "__main__":
    sys.exit(main())
