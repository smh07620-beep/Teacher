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
