"""Dedicated Teacher AI worker backed by persistent domain-specific queues."""
from __future__ import annotations

import importlib.util
import os
import socket
import sys
import threading
import time

from teacher_app.assessments import ai_jobs, free_ai_fallback
from teacher_app.assessments.question_runtime import build_canonical_question_runtime
from teacher_app.materials import (
    ai_presentation_jobs,
    ai_video_jobs,
    ai_video_renderer,
    media_audio_jobs,
    media_script_jobs,
    media_subtitle_jobs,
)
from teacher_app.worker import repository as worker_repository


def _env_int(name: str, default: int, lower: int, upper: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)) or default)
    except (TypeError, ValueError):
        value = default
    return max(lower, min(upper, value))


def log(message: str) -> None:
    print(f"[teacher-ai-worker] {message}", flush=True)


def _ai_worker_id() -> str:
    base = str(os.environ.get("MATERIAL_WORKER_ID") or socket.gethostname() or "teacher-worker").strip()
    safe = "".join(char if char.isalnum() or char in "._-" else "-" for char in base)[:90].strip("-") or "teacher-worker"
    return f"{safe}-ai"[:100]


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _ai_worker_capabilities() -> dict:
    kokoro_ready = _module_available("kokoro")
    numpy_ready = _module_available("numpy")
    misaki_ready = _module_available("misaki")
    whisper_ready = _module_available("faster_whisper")
    return {
        "workerKind": "ai",
        "workerMachine": str(socket.gethostname() or "")[:80],
        "heartbeatContract": 2,
        "heartbeatTransport": "database",
        "kokoro": {
            "available": bool(kokoro_ready and numpy_ready and misaki_ready),
            "kokoro": kokoro_ready,
            "numpy": numpy_ready,
            "misaki": misaki_ready,
        },
        "whisper": {"available": whisper_ready},
        "queues": ["ai_questions", "media_scripts", "ai_presentations", "ai_videos", "media_audio", "media_subtitles"],
    }


class _AIHeartbeat:
    def __init__(self, interval_seconds: int = 30):
        self.worker_id = _ai_worker_id()
        self.interval_seconds = max(10, min(90, int(interval_seconds or 30)))
        self.failure_limit = _env_int("AI_WORKER_HEARTBEAT_FAILURE_LIMIT", 5, 2, 20)
        self.startup_attempts = _env_int("AI_WORKER_HEARTBEAT_STARTUP_ATTEMPTS", 3, 1, 10)
        self._stop = threading.Event()
        self._fatal = threading.Event()
        self._thread = None
        self._consecutive_failures = 0

    def pulse(self) -> None:
        stamp = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        worker_repository.upsert_heartbeat(
            self.worker_id,
            last_seen=stamp,
            capabilities=_ai_worker_capabilities(),
            current_job_id="",
        )

    def _pulse_once(self) -> bool:
        try:
            self.pulse()
        except Exception as exc:
            self._consecutive_failures += 1
            log(
                "heartbeat write failed "
                f"type={type(exc).__name__} consecutive={self._consecutive_failures}/{self.failure_limit}"
            )
            if self._consecutive_failures >= self.failure_limit:
                self._fatal.set()
            return False
        if self._consecutive_failures:
            log("heartbeat write recovered")
        self._consecutive_failures = 0
        return True

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self._pulse_once()
            if self._fatal.is_set():
                return

    def raise_if_unhealthy(self) -> None:
        if self._fatal.is_set():
            raise RuntimeError(
                "AI Worker heartbeat has repeatedly failed; refusing to remain falsely healthy."
            )

    def __enter__(self):
        for attempt in range(1, self.startup_attempts + 1):
            if self._pulse_once():
                break
            if attempt < self.startup_attempts:
                time.sleep(min(5, attempt * 2))
        else:
            raise RuntimeError(
                "AI Worker startup heartbeat could not be persisted to the production database."
            )
        self._thread = threading.Thread(target=self._run, name="teacher-ai-heartbeat", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        return False


def _renderer_status_line() -> str:
    summary = ai_video_renderer.capability_summary()
    states = ",".join(
        f"{item.get('id')}:{'candidate' if item.get('candidate') else 'unavailable'}"
        for item in summary.get("candidates", [])
    )
    return f"video_renderers={states} selected_candidate={summary.get('selectedCandidate') or 'text-fallback'}"


def main() -> int:
    question_runtime = build_canonical_question_runtime()
    free_ai_fallback.install_question_runtime_fallback(question_runtime)
    question_processor = ai_jobs.AiQuestionJobProcessor(question_runtime)
    script_processor = media_script_jobs.MediaScriptJobProcessor()
    presentation_processor = ai_presentation_jobs.AiPresentationJobProcessor()
    video_processor = ai_video_jobs.AiVideoJobProcessor()
    audio_processor = media_audio_jobs.MediaAudioJobProcessor()
    subtitle_processor = media_subtitle_jobs.MediaSubtitleJobProcessor()
    poll_seconds = _env_int("AI_QUESTION_WORKER_POLL_SECONDS", 2, 1, 30)
    recovery_seconds = _env_int("AI_QUESTION_WORKER_RECOVERY_SECONDS", 300, 30, 3600)
    next_recovery = 0.0
    log(
        "started queues=ai_questions,media_scripts,ai_presentations,ai_videos,media_audio,media_subtitles "
        "free_fallback=enabled"
    )
    log(_renderer_status_line())
    heartbeat_seconds = _env_int("AI_WORKER_HEARTBEAT_SECONDS", 30, 10, 90)
    with _AIHeartbeat(heartbeat_seconds) as heartbeat:
        while True:
            try:
                heartbeat.raise_if_unhealthy()
                now = time.monotonic()
                if now >= next_recovery:
                    recovered_questions = question_processor.recover_stale()
                    recovered_scripts = script_processor.recover_stale()
                    recovered_presentations = presentation_processor.recover_stale()
                    recovered_videos = video_processor.recover_stale()
                    recovered_audio = audio_processor.recover_stale()
                    recovered_subtitles = subtitle_processor.recover_stale()
                    if (
                        recovered_questions
                        or recovered_scripts
                        or recovered_presentations
                        or recovered_videos
                        or recovered_audio
                        or recovered_subtitles
                    ):
                        log(
                            "requeued stale "
                            f"question_jobs={recovered_questions} media_script_jobs={recovered_scripts} "
                            f"ai_presentation_jobs={recovered_presentations} media_audio_jobs={recovered_audio} "
                            f"ai_video_jobs={recovered_videos} "
                            f"media_subtitle_jobs={recovered_subtitles}"
                        )
                    next_recovery = now + recovery_seconds

                # Give every domain queue one chance per loop. A large assessment queue
                # must not starve teacher script or narration work; PowerPoint and subtitle
                # queues receive the same one-job-per-loop fairness guarantee.
                did_work = question_processor.run_next_queued()
                did_work = script_processor.run_next_queued() or did_work
                did_work = presentation_processor.run_next_queued() or did_work
                did_work = video_processor.run_next_queued() or did_work
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
                # Keep the worker alive and retry without claiming a job twice. Do not
                # print raw provider/DB exception text because it may contain secrets.
                log(f"loop error type={type(exc).__name__}")
                time.sleep(poll_seconds)


if __name__ == "__main__":
    sys.exit(main())
