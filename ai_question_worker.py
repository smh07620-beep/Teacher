"""Dedicated Teacher AI worker backed by persistent domain-specific queues."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

# Resolve a stable Hugging Face cache before importing Worker modules that may
# transitively import huggingface_hub. An explicit .local-worker.env value wins.
_hf_home = str(os.environ.get("HF_HOME") or "").strip()
if _hf_home:
    os.environ["HF_HOME"] = str(Path(os.path.expandvars(_hf_home)).expanduser())
else:
    _hf_base = str(os.environ.get("LOCALAPPDATA") or os.environ.get("PROGRAMDATA") or "").strip()
    _hf_path = (Path(_hf_base) / "Teacher" / "huggingface") if _hf_base else (Path.home() / ".cache" / "Teacher" / "huggingface")
    os.environ["HF_HOME"] = str(_hf_path)

from teacher_app import config as teacher_config
from teacher_app.assessments import ai_jobs, free_ai_fallback
from teacher_app.assessments.question_runtime import build_canonical_question_runtime
from teacher_app.materials import (
    ai_presentation_jobs,
    ai_video_jobs,
    ai_video_renderer,
    media_audio_runtime,
    media_audio_jobs,
    media_audio_runtime,
    media_script_jobs,
    media_subtitle_jobs,
)
from teacher_app.worker import ai_remote
from teacher_app.worker import repository as worker_repository


if os.environ.get("TEACHER_E2E_DETERMINISTIC_STUBS") == "1":
    # This is deliberately loaded by the Worker, not Web: routes still create
    # real durable jobs and production processes cannot enter this path without
    # the second test-only opt-in enforced by the helper.
    from teacher_app.testing import deterministic_ai_provider

    deterministic_ai_provider.install()


_KOKORO_STARTUP_STATE: dict = {}


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


def _worker_build_identity() -> dict:
    root = Path(__file__).resolve().parent
    try:
        version = (root / "VERSION").read_text(encoding="utf-8").strip()[:32]
    except OSError:
        version = ""
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
        sha = str(completed.stdout or "").strip().lower() if completed.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        sha = ""
    try:
        completed = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
        branch = str(completed.stdout or "").strip()[:80] if completed.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        branch = ""
    return {"workerVersion": version, "workerSha": sha[:40], "workerBranch": branch}


def _ai_worker_capabilities(transport: str | None = None) -> dict:
    transport = transport or ai_remote.transport_mode()
    kokoro_ready = _module_available("kokoro")
    numpy_ready = _module_available("numpy")
    misaki_ready = _module_available("misaki")
    whisper_ready = _module_available("faster_whisper")
    web_mode = transport == ai_remote.TRANSPORT_HTTPS
    payload = {
        **_worker_build_identity(),
        "workerKind": "ai",
        "workerMachine": str(socket.gethostname() or "")[:80],
        "heartbeatContract": 4 if web_mode else 2,
        "heartbeatTransport": "https" if web_mode else "database",
        "controlPlaneReady": web_mode,
        "databaseReady": None if web_mode else True,
        "databaseIdentity": "" if web_mode else teacher_config.database_identity(),
        "kokoro": {
            "available": bool(kokoro_ready and numpy_ready and misaki_ready),
            "kokoro": kokoro_ready,
            "numpy": numpy_ready,
            "misaki": misaki_ready,
        },
        "tts": {
            "provider": "kokoro-local",
            "repoId": str(os.environ.get("KOKORO_REPO_ID") or media_audio_runtime.DEFAULT_REPO_ID)[:160],
            "model": str(os.environ.get("KOKORO_MODEL") or media_audio_runtime.DEFAULT_MODEL)[:120],
            "defaultVoice": media_audio_runtime._voice(
                os.environ.get("KOKORO_VOICE") or media_audio_runtime.DEFAULT_VOICE
            ),
            "warmup": bool(_KOKORO_STARTUP_STATE.get("warmed")),
            "device": str(_KOKORO_STARTUP_STATE.get("device") or "")[:40],
            "cudaAvailable": _KOKORO_STARTUP_STATE.get("cudaAvailable"),
        },
        "whisper": {"available": whisper_ready},
        "queues": ["ai_questions", "media_scripts", "ai_presentations", "ai_videos", "media_audio", "media_subtitles"],
    }
    if os.environ.get("TEACHER_E2E_DETERMINISTIC_STUBS") == "1":
        payload = deterministic_ai_provider.tts_capabilities(payload)
    return payload


class _AIHeartbeat:
    def __init__(
        self,
        interval_seconds: int = 30,
        *,
        transport: str | None = None,
        api: ai_remote.AIWorkerApi | None = None,
    ):
        self.worker_id = _ai_worker_id()
        self.interval_seconds = max(10, min(90, int(interval_seconds or 30)))
        self.transport = transport or ai_remote.transport_mode()
        self.api = api
        self.failure_limit = _env_int("AI_WORKER_HEARTBEAT_FAILURE_LIMIT", 5, 2, 20)
        self.startup_attempts = _env_int("AI_WORKER_HEARTBEAT_STARTUP_ATTEMPTS", 3, 1, 10)
        self._stop = threading.Event()
        self._fatal = threading.Event()
        self._thread = None
        self._consecutive_failures = 0

    def pulse(self) -> None:
        capabilities = _ai_worker_capabilities(self.transport)
        if self.transport == ai_remote.TRANSPORT_HTTPS:
            if self.api is None:
                raise RuntimeError("AI Worker HTTPS client 尚未初始化。")
            self.api.heartbeat(capabilities)
            return

        stamp = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        worker_repository.upsert_heartbeat(
            self.worker_id,
            last_seen=stamp,
            capabilities=capabilities,
            current_job_id="",
        )

    def _pulse_once(self) -> bool:
        try:
            self.pulse()
        except Exception as exc:
            self._consecutive_failures += 1
            log(
                "heartbeat write failed "
                f"transport={self.transport} type={type(exc).__name__} "
                f"consecutive={self._consecutive_failures}/{self.failure_limit}"
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

    def is_unhealthy(self) -> bool:
        return self._fatal.is_set()

    def __enter__(self):
        for attempt in range(1, self.startup_attempts + 1):
            if self._pulse_once():
                break
            if attempt < self.startup_attempts:
                time.sleep(min(5, attempt * 2))
        else:
            raise RuntimeError(
                f"AI Worker startup heartbeat could not reach the {self.transport} control plane."
            )
        self._thread = threading.Thread(target=self._run, name="teacher-ai-heartbeat", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        return False


def _warm_kokoro_on_startup() -> dict:
    """Warm Kokoro before queue polling without making Worker startup brittle."""
    global _KOKORO_STARTUP_STATE
    try:
        state = media_audio_runtime.preload_kokoro()
    except Exception as exc:
        state = {
            "warmed": False,
            "device": "",
            "cudaAvailable": None,
            "errorType": type(exc).__name__,
        }
        _KOKORO_STARTUP_STATE = state
        log(f"kokoro preload failed type={type(exc).__name__}; lazy retry enabled")
        return state

    _KOKORO_STARTUP_STATE = dict(state)
    loaded = len(state.get("loadedVoices") or [])
    timings = state.get("timings") or {}
    log(
        "kokoro preload ready "
        f"device={state.get('device') or 'unknown'} "
        f"cuda_available={bool(state.get('cudaAvailable'))} "
        f"voices_cached={loaded} hf_cache=persistent "
        f"hf_offline={bool(state.get('hfOffline'))} "
        + " ".join(f"{key}={value}s" for key, value in timings.items())
    )
    return state


# Set once the (background) Kokoro warmup finished or failed.  The audio queue
# waits for it so a job never races the one-time Torch/Kokoro load; every other
# queue starts immediately instead of waiting behind the TTS warmup.
_KOKORO_WARM_DONE = threading.Event()


def _kokoro_warm_thread_body() -> None:
    try:
        _warm_kokoro_on_startup()
    finally:
        _KOKORO_WARM_DONE.set()


def _start_kokoro_warmup() -> None:
    """Warm Kokoro in the background (default) or inline when AI_WORKER_KOKORO_WARM_BLOCKING=true."""
    blocking = str(os.environ.get("AI_WORKER_KOKORO_WARM_BLOCKING", "false")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if blocking:
        _kokoro_warm_thread_body()
        return
    threading.Thread(target=_kokoro_warm_thread_body, name="teacher-kokoro-warmup", daemon=True).start()


def _renderer_status_line() -> str:
    summary = ai_video_renderer.capability_summary()
    states = ",".join(
        f"{item.get('id')}:{'candidate' if item.get('candidate') else 'unavailable'}"
        for item in summary.get("candidates", [])
    )
    return f"video_renderers={states} selected_candidate={summary.get('selectedCandidate') or 'text-fallback'}"


def main() -> int:
    transport = ai_remote.transport_mode()
    api = None
    if transport == ai_remote.TRANSPORT_HTTPS:
        api = ai_remote.AIWorkerApi(worker_id=_ai_worker_id())
        ai_remote.install_remote_repository_proxies(api)

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
        f"free_fallback=enabled control_transport={transport}"
    )
    log(_renderer_status_line())
    heartbeat_seconds = _env_int("AI_WORKER_HEARTBEAT_SECONDS", 30, 10, 90)
    try:
        with _AIHeartbeat(heartbeat_seconds, transport=transport, api=api) as heartbeat:
            # Publish heartbeat first, then pay the one-time Kokoro/Torch load
            # cost in the background so non-TTS queues start immediately.  The
            # warmup helper is the only startup owner of preload_kokoro().
            _start_kokoro_warmup()
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

                    # Give every domain queue one chance per loop.  In HTTPS mode
                    # these are tiny authenticated JSON RPC calls; large source and
                    # artifact bytes still move directly through durable storage.
                    did_work = question_processor.run_next_queued()
                    did_work = script_processor.run_next_queued() or did_work
                    did_work = presentation_processor.run_next_queued() or did_work
                    if _KOKORO_WARM_DONE.is_set():
                        did_work = video_processor.run_next_queued() or did_work
                    if _KOKORO_WARM_DONE.is_set():
                        did_work = audio_processor.run_next_queued() or did_work
                    did_work = subtitle_processor.run_next_queued() or did_work
                    if did_work:
                        continue
                    time.sleep(poll_seconds)
                except KeyboardInterrupt:
                    log("stopped")
                    return 0
                except Exception as exc:
                    # Network/provider services may recover after startup.  Never
                    # print raw provider/DB exception text because it may contain
                    # credentials. A dead heartbeat control plane requests a clean
                    # supervisor restart instead of staying falsely RUNNING.
                    log(f"loop error type={type(exc).__name__}")
                    if heartbeat.is_unhealthy():
                        return 75
                    time.sleep(poll_seconds)
    finally:
        if api is not None:
            api.close()


if __name__ == "__main__":
    sys.exit(main())
