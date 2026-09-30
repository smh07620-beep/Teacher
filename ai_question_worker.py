"""Dedicated Teacher AI worker backed by persistent domain-specific queues."""
from __future__ import annotations

import os
import sys
import time

from teacher_app.assessments import ai_jobs, free_ai_fallback
from teacher_app.assessments.question_runtime import build_canonical_question_runtime
from teacher_app.materials import media_audio_jobs, media_script_jobs, media_subtitle_jobs


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
    free_ai_fallback.install_question_runtime_fallback(question_runtime)
    question_processor = ai_jobs.AiQuestionJobProcessor(question_runtime)
    script_processor = media_script_jobs.MediaScriptJobProcessor()
    audio_processor = media_audio_jobs.MediaAudioJobProcessor()
    subtitle_processor = media_subtitle_jobs.MediaSubtitleJobProcessor()
    poll_seconds = _env_int("AI_QUESTION_WORKER_POLL_SECONDS", 2, 1, 30)
    recovery_seconds = _env_int("AI_QUESTION_WORKER_RECOVERY_SECONDS", 300, 30, 3600)
    next_recovery = 0.0
    log("started queues=ai_questions,media_scripts,media_audio,media_subtitles free_fallback=enabled")
    while True:
        try:
            now = time.monotonic()
            if now >= next_recovery:
                recovered_questions = question_processor.recover_stale()
                recovered_scripts = script_processor.recover_stale()
                recovered_audio = audio_processor.recover_stale()
                recovered_subtitles = subtitle_processor.recover_stale()
                if recovered_questions or recovered_scripts or recovered_audio or recovered_subtitles:
                    log(
                        "requeued stale "
                        f"question_jobs={recovered_questions} media_script_jobs={recovered_scripts} "
                        f"media_audio_jobs={recovered_audio} media_subtitle_jobs={recovered_subtitles}"
                    )
                next_recovery = now + recovery_seconds

            # Give every domain queue one chance per loop.  A large assessment
            # queue must not starve teacher script, narration, or subtitle work.
            did_work = question_processor.run_next_queued()
            did_work = script_processor.run_next_queued() or did_work
            did_work = audio_processor.run_next_queued() or did_work
            did_work = subtitle_processor.run_next_queued() or did_work
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
