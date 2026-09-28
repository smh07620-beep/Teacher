"""Dedicated Teacher AI worker backed by persistent domain-specific queues."""
from __future__ import annotations

import os
import sys
import time

from teacher_app.assessments import ai_jobs
from teacher_app.assessments.question_runtime import build_canonical_question_runtime
from teacher_app.materials import media_script_jobs


def _env_int(name: str, default: int, lower: int, upper: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)) or default)
    except (TypeError, ValueError):
        value = default
    return max(lower, min(upper, value))


def log(message: str) -> None:
    print(f"[teacher-ai-worker] {message}", flush=True)


def main() -> int:
    question_runtime = build_canonical_question_runtime()
    question_processor = ai_jobs.AiQuestionJobProcessor(question_runtime)
    script_processor = media_script_jobs.MediaScriptJobProcessor()
    poll_seconds = _env_int("AI_QUESTION_WORKER_POLL_SECONDS", 2, 1, 30)
    recovery_seconds = _env_int("AI_QUESTION_WORKER_RECOVERY_SECONDS", 300, 30, 3600)
    next_recovery = 0.0
    log("started queues=ai_questions,media_scripts")
    while True:
        try:
            now = time.monotonic()
            if now >= next_recovery:
                recovered_questions = question_processor.recover_stale()
                recovered_scripts = script_processor.recover_stale()
                if recovered_questions or recovered_scripts:
                    log(
                        "requeued stale "
                        f"question_jobs={recovered_questions} media_script_jobs={recovered_scripts}"
                    )
                next_recovery = now + recovery_seconds

            # Give both domain queues one chance per loop.  Do not let a large
            # assessment queue permanently starve teacher media-script work.
            did_work = question_processor.run_next_queued()
            did_work = script_processor.run_next_queued() or did_work
            if did_work:
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
