"""Test-only process bootstrap for isolated F/G AI Worker."""
from __future__ import annotations
import os

if os.environ.get("TEACHER_E2E_TEST_MODE") == "1" and os.environ.get("TEACHER_E2E_DETERMINISTIC_STUBS") == "1":
    from teacher_app.materials import media_subtitle_runtime

    def _deterministic_segments(_path, **_kwargs):
        return (
            [
                {"start": 0.0, "end": 0.9, "text": "E2E 字幕：先核對病人識別與檢體品質。"},
                {"start": 0.9, "end": 2.2, "text": "播放到一秒後進入時間點考題。"},
            ],
            {"provider": "deterministic-e2e", "model": "deterministic-subtitle-v1", "fallbackUsed": False},
        )

    media_subtitle_runtime.transcribe_segments = _deterministic_segments


# Keep the real FFmpeg command path but expose stderr in isolated CI failures.
# Production runtime intentionally keeps user-facing errors terse; this seam
# makes the E2E job actionable without changing production behavior.
if os.environ.get("TEACHER_E2E_TEST_MODE") == "1" and os.environ.get("TEACHER_E2E_DETERMINISTIC_STUBS") == "1":
    import subprocess
    from teacher_app.materials import ai_video_runtime

    def _diagnostic_run(command, *, timeout, message):
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        except FileNotFoundError as exc:
            raise RuntimeError(message) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"{message}（逾時）") from exc
        if completed.returncode != 0:
            detail = " ".join((completed.stderr or completed.stdout or "").split())[-1200:]
            raise RuntimeError(f"{message}（exit={completed.returncode}）｜{detail}")

    ai_video_runtime._run = _diagnostic_run
