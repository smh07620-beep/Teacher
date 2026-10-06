"""Deterministic local provider used only by the isolated full-stack CI job.

It replaces provider inference, never queue/repository/storage/renderer code.  The
double opt-in makes an accidental production activation fail closed.
"""
from __future__ import annotations

import io
import math
import os
import struct
import wave


ENVIRONMENT_FLAG = "TEACHER_E2E_DETERMINISTIC_STUBS"


def enabled() -> bool:
    return (
        os.environ.get(ENVIRONMENT_FLAG) == "1"
        and os.environ.get("TEACHER_E2E_TEST_MODE") == "1"
    )


def _wav(*_args, **_kwargs):
    """Return a small valid mono WAV without importing/downloading Kokoro."""
    sample_rate = 24_000
    frames = bytearray()
    for index in range(sample_rate):
        value = int(2_800 * math.sin(2 * math.pi * 440 * index / sample_rate))
        frames.extend(struct.pack("<h", value))
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(bytes(frames))
    return output.getvalue(), "deterministic-kokoro-stub"


def install() -> None:
    """Install only inference seams; all durable contracts remain canonical."""
    if not enabled():
        raise RuntimeError("deterministic provider is restricted to isolated E2E CI")

    os.environ["GROQ_API_KEY"] = "isolated-e2e-not-a-real-key"
    os.environ["AI_PROVIDER"] = "groq"

    from teacher_app.assessments import ai_runtime
    from teacher_app.materials import ai_video_runtime, media_audio_runtime, media_script_runtime

    def questions(materials, *, count=1, qtype="choice", **_kwargs):
        source = materials[0] if materials else {}
        chunks = []
        for material in materials:
            text, _ = ai_runtime.extract_material_text_for_ai(material)
            chunks.extend(ai_runtime.build_retrieval_chunks(material, text))
        media_url = f"/view/{source.get('id', '')}" if str(qtype).startswith("video_") else ""
        question_type = "video" if media_url else "choice"
        result = []
        for number in range(max(1, min(int(count or 1), 3))):
            config = {"mediaUrl": media_url, "pauseAt": 1} if media_url else {}
            result.append({
                "question": f"E2E deterministic question {number + 1}: 哪一項是教材重點？",
                "questionType": question_type,
                "options": ["正確重點", "錯誤敘述", "不適用", "未提及"],
                "correct": 0,
                "answerConfig": config,
                "tag": "E2E",
                "difficulty": "standard",
                "explanation": "由 deterministic provider 根據已選教材建立。",
            })
        return ai_runtime.attach_question_provenance(result, chunks)

    ai_runtime.ai_question_is_configured = lambda _settings=None: True
    # Keep the canonical provider key so the production fallback dispatcher
    # still invokes the real runtime contract; only inference is replaced.
    ai_runtime.active_ai_provider = lambda _settings=None: "groq"
    ai_runtime.ai_model_name = lambda _settings=None: "deterministic-e2e-v1"
    ai_runtime.generate_groq_multisource_candidates = questions

    def text_provider(_settings, _provider, _prompt, progress_callback=None):
        if progress_callback:
            progress_callback(70, "deterministic provider", "isolated CI provider completed")
        return (
            "第 1 張：E2E 教學重點\n- 由來源教材建立可追溯大綱\n- 教師需核准後發布\n"
            "第 2 張：安全流程\n- 核對來源\n- 記錄品質與 provenance\n"
            "本講稿供教師修改、核准與後續配音／影片製作使用。",
            {"provider": "deterministic-e2e", "model": "deterministic-e2e-v1", "fallbackUsed": False, "attemptedProviders": ["deterministic-e2e"]},
        )

    media_script_runtime._generate_body_with_fallback = text_provider
    media_audio_runtime._synthesize = _wav
    ai_video_runtime._synthesize = _wav
    media_audio_runtime.preload_kokoro = lambda: {
        "warmed": True, "device": "deterministic", "cudaAvailable": False, "loadedVoices": ["zf_001"],
    }
