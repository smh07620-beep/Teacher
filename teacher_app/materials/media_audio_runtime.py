"""Approved teacher script -> local Kokoro narration -> durable R2 material.

The Web process only validates configuration/enqueues jobs. Kokoro inference is
loaded lazily inside the dedicated local AI Worker so Render never needs the
large TTS runtime and no paid OpenAI TTS request is made.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import threading
import time
import wave
from typing import Any, Callable

from teacher_app.materials import repository as material_repository
from teacher_app.materials import tts_text
from teacher_app.storage import providers, r2_budget, r2_ledger


AI_DISCLOSURE = "本音訊為本機 AI 合成語音，內容來源為授課教師已核准之教學講稿。"
VOICE_PREVIEW_TEXT = "您好，這是醫學檢驗教學平台的 AI 語音試聽。"
DEFAULT_PROVIDER = "kokoro"
DEFAULT_MODEL = "Kokoro-82M-v1.1-zh"
DEFAULT_REPO_ID = "hexgrad/Kokoro-82M-v1.1-zh"
DEFAULT_VOICE = "zf_001"
DEFAULT_SAMPLE_RATE = 24000
# Silence between two slide segments inside the single narration WAV.  The learner
# player pauses at each segment's endMs, so this must stay longer than its
# polling interval to guarantee the next slide's first word is never played early.
SEGMENT_GAP_MS = 400
ALLOWED_VOICES = {
    "zf_001",
    "zf_002",
    "zf_003",
    "zf_004",
    "zm_009",
    "zm_010",
    "zm_011",
    "zm_012",
}
VOICE_LABELS = {
    "zf_001": "中文女聲 A",
    "zf_002": "中文女聲 B",
    "zf_003": "中文女聲 C",
    "zf_004": "中文女聲 D",
    "zm_009": "中文男聲 A",
    "zm_010": "中文男聲 B",
    "zm_011": "中文男聲 C",
    "zm_012": "中文男聲 D",
}
LEGACY_VOICE_ALIASES = {
    "zf_xiaoxiao": "zf_001",
    "zf_xiaobei": "zf_002",
    "zf_xiaoni": "zf_003",
    "zf_xiaoyi": "zf_004",
    "zm_yunxi": "zm_009",
    "zm_yunjian": "zm_010",
    "zm_yunxia": "zm_011",
    "zm_yunyang": "zm_012",
}


_KOKORO_PIPELINE = None
_KOKORO_PIPELINE_KEY = ""
_KOKORO_PIPELINE_LOCK = threading.Lock()
_TTS_CACHE_CLEANED_AT = 0.0
_HF_OFFLINE_AUTO = False


def _repo_id() -> str:
    repo_id = str(os.environ.get("KOKORO_REPO_ID") or DEFAULT_REPO_ID).strip() or DEFAULT_REPO_ID
    return DEFAULT_REPO_ID if repo_id == "hexgrad/Kokoro-82M" else repo_id


def _tts_speed() -> float:
    try:
        speed = float(os.environ.get("KOKORO_TTS_SPEED", "1.0") or 1.0)
    except (TypeError, ValueError):
        speed = 1.0
    return max(0.75, min(1.35, speed))


def _ensure_hf_home() -> str:
    """Keep Hugging Face model/voice downloads in a persistent Worker cache."""
    configured = str(os.environ.get("HF_HOME") or "").strip()
    if configured:
        cache_path = Path(os.path.expandvars(configured)).expanduser()
    else:
        base = str(os.environ.get("LOCALAPPDATA") or os.environ.get("PROGRAMDATA") or "").strip()
        cache_path = (Path(base) / "Teacher" / "huggingface") if base else (Path.home() / ".cache" / "Teacher" / "huggingface")
    try:
        cache_path.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Kokoro/Hugging Face will surface a concrete cache error later.  Do not
        # make Worker startup fail only because this proactive mkdir failed.
        pass
    resolved = str(cache_path)
    os.environ["HF_HOME"] = resolved
    return resolved


def _hf_hub_cache_dir() -> Path:
    configured = str(os.environ.get("HF_HUB_CACHE") or os.environ.get("HUGGINGFACE_HUB_CACHE") or "").strip()
    if configured:
        return Path(os.path.expandvars(configured)).expanduser()
    return Path(_ensure_hf_home()) / "hub"


def _kokoro_assets_cached(repo_id: str, voice: str) -> bool:
    """True when the model weights, config and the given voice are all in the HF cache."""
    snapshots = _hf_hub_cache_dir() / ("models--" + repo_id.replace("/", "--")) / "snapshots"
    try:
        for snapshot in snapshots.iterdir():
            if not (snapshot / "config.json").is_file():
                continue
            if not any(snapshot.glob("*.pth")):
                continue
            if (snapshot / "voices" / f"{voice}.pt").is_file():
                return True
    except OSError:
        return False
    return False


def _set_hf_offline(enabled: bool) -> None:
    if enabled:
        os.environ["HF_HUB_OFFLINE"] = "1"
    else:
        os.environ.pop("HF_HUB_OFFLINE", None)
    # huggingface_hub reads the flag at import time; update it if already loaded.
    constants = getattr(sys.modules.get("huggingface_hub"), "constants", None)
    if constants is not None:
        try:
            constants.HF_HUB_OFFLINE = bool(enabled)
        except Exception:
            pass


def _configure_hf_offline(repo_id: str, voice: str) -> bool:
    """Skip Hugging Face network checks on every Worker start once assets are cached.

    KOKORO_HF_OFFLINE=auto (default) enables offline mode only when the model and
    the default voice are already cached; 1 forces it on; 0 forces it off.  An
    explicit HF_HUB_OFFLINE in the environment is always respected.  When
    auto-enabled, synthesis of a not-yet-cached voice re-enables the network
    once (see ``_disable_auto_hf_offline``).
    """
    global _HF_OFFLINE_AUTO
    if str(os.environ.get("HF_HUB_OFFLINE") or "").strip():
        return False
    mode = str(os.environ.get("KOKORO_HF_OFFLINE") or "auto").strip().lower()
    if mode in {"0", "false", "no", "off"}:
        return False
    if mode in {"1", "true", "yes", "on"}:
        _set_hf_offline(True)
        return True
    if _kokoro_assets_cached(repo_id, voice):
        _set_hf_offline(True)
        _HF_OFFLINE_AUTO = True
        return True
    return False


def _disable_auto_hf_offline() -> bool:
    """Undo auto offline mode (e.g. a voice that is not cached yet needs a download)."""
    global _HF_OFFLINE_AUTO
    if not _HF_OFFLINE_AUTO:
        return False
    _HF_OFFLINE_AUTO = False
    _set_hf_offline(False)
    return True


def _tts_cache_root() -> Path:
    configured = str(os.environ.get("KOKORO_CACHE_DIR") or "").strip()
    if configured:
        return Path(os.path.expandvars(configured)).expanduser()
    return Path(_ensure_hf_home()).parent / "kokoro-tts"


def _normalized_text(text: str) -> str:
    return " ".join(str(text or "").replace("\x00", " ").split())


def tts_cache_key(text: str, *, repo_id: str, voice: str, speed: float) -> str:
    payload = [repo_id, _voice(voice), round(float(speed), 2), _normalized_text(text)]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def _clean_tts_cache(root: Path) -> None:
    global _TTS_CACHE_CLEANED_AT
    now = dt.datetime.now().timestamp()
    if now - _TTS_CACHE_CLEANED_AT < 3600:
        return
    _TTS_CACHE_CLEANED_AT = now
    try:
        expiry = now - max(1, min(90, int(os.environ.get("KOKORO_TTS_CACHE_DAYS", "14") or 14))) * 86400
        for path in root.glob("*.wav"):
            if path.stat().st_mtime < expiry:
                path.unlink(missing_ok=True)
    except OSError:
        pass


def _pipeline_device(pipeline) -> str:
    model = getattr(pipeline, "model", None)
    if model is not None:
        try:
            return str(next(model.parameters()).device)
        except (AttributeError, StopIteration, TypeError):
            device = getattr(model, "device", None)
            if device is not None:
                return str(device)
    return "unknown"


def preload_kokoro() -> dict[str, Any]:
    """Download/cache Kokoro assets and warm the default Chinese voice once."""
    hf_home = _ensure_hf_home()
    repo_id = _repo_id()
    voice = _voice(os.environ.get("KOKORO_VOICE") or DEFAULT_VOICE)
    speed = _tts_speed()
    timings: dict[str, float] = {}
    started = time.monotonic()
    offline = _configure_hf_offline(repo_id, voice)

    mark = time.monotonic()
    try:
        import torch
        cuda_available = bool(torch.cuda.is_available())
    except Exception:
        cuda_available = False
    timings["importTorch"] = round(time.monotonic() - mark, 2)

    mark = time.monotonic()
    pipeline = _kokoro_pipeline(repo_id)
    timings["createPipeline"] = round(time.monotonic() - mark, 2)

    # Only the default voice is loaded at startup.  Other voices are loaded by
    # Kokoro the first time they are selected (and cached in memory/HF cache),
    # so startup no longer pays for every selectable voice file.  Set
    # KOKORO_PRELOAD_ALL_VOICES=true to prime every voice like the old behaviour.
    mark = time.monotonic()
    loaded_voices = []
    preload_all = str(os.environ.get("KOKORO_PRELOAD_ALL_VOICES", "false")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    candidates = sorted(ALLOWED_VOICES) if preload_all else [voice]
    load_voice = getattr(pipeline, "load_voice", None)
    if callable(load_voice):
        for candidate in candidates:
            try:
                load_voice(candidate)
                loaded_voices.append(candidate)
            except Exception:
                continue
    timings["loadVoices"] = round(time.monotonic() - mark, 2)

    mark = time.monotonic()
    produced_audio = False
    for result in pipeline("你好", voice=voice, speed=speed, split_pattern=r"\n+"):
        audio = getattr(result, "audio", None)
        if audio is None and isinstance(result, (tuple, list)) and len(result) >= 3:
            audio = result[2]
        if audio is not None:
            produced_audio = True
    if not produced_audio:
        raise RuntimeError("Kokoro 暖機沒有產生有效音訊。")
    timings["firstSynthesis"] = round(time.monotonic() - mark, 2)
    timings["total"] = round(time.monotonic() - started, 2)

    return {
        "warmed": True,
        "hfOffline": bool(offline),
        "timings": timings,
        "repoId": repo_id,
        "voice": voice,
        "speed": speed,
        "cudaAvailable": cuda_available,
        "device": _pipeline_device(pipeline),
        "hfHome": hf_home,
        "loadedVoices": loaded_voices,
    }


def _kokoro_pipeline(repo_id: str):
    """Lazily load Kokoro once per Worker process instead of once per preview/job."""
    global _KOKORO_PIPELINE, _KOKORO_PIPELINE_KEY
    key = f"z::{repo_id}"
    if _KOKORO_PIPELINE is not None and _KOKORO_PIPELINE_KEY == key:
        return _KOKORO_PIPELINE
    with _KOKORO_PIPELINE_LOCK:
        if _KOKORO_PIPELINE is not None and _KOKORO_PIPELINE_KEY == key:
            return _KOKORO_PIPELINE
        try:
            import torch
            torch.set_num_threads(max(1, min(4, int(os.environ.get("KOKORO_TORCH_THREADS", "2") or 2))))
        except Exception:
            pass
        from kokoro import KPipeline
        _KOKORO_PIPELINE = KPipeline(lang_code="z", repo_id=repo_id)
        _KOKORO_PIPELINE_KEY = key
        return _KOKORO_PIPELINE


def _provider() -> str:
    value = str(os.environ.get("AI_TTS_PROVIDER") or DEFAULT_PROVIDER).strip().lower()
    # Paid/cloud TTS is intentionally disabled in FREE_ONLY_MODE. Keep the
    # fallback local even if a stale Render variable still says "openai".
    if str(os.environ.get("FREE_ONLY_MODE", "true")).strip().lower() in {"1", "true", "yes", "on"}:
        return DEFAULT_PROVIDER
    return value if value == DEFAULT_PROVIDER else DEFAULT_PROVIDER


def configured() -> bool:
    return _provider() == DEFAULT_PROVIDER and providers.r2_is_configured()


def public_status() -> dict[str, Any]:
    return {
        "enabled": configured(),
        "r2Ready": providers.r2_is_configured(),
        "providerReady": _provider() == DEFAULT_PROVIDER,
        "provider": "kokoro-local" if configured() else "",
        "model": str(os.environ.get("KOKORO_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        "defaultVoice": _voice(os.environ.get("KOKORO_VOICE", DEFAULT_VOICE)),
        "voices": sorted(ALLOWED_VOICES),
        "voiceOptions": [
            {"id": voice, "label": VOICE_LABELS.get(voice, voice)}
            for voice in sorted(ALLOWED_VOICES)
        ],
        "previewSupported": True,
        "requiresApprovedScript": True,
        "storesToR2": True,
        "localWorkerRequired": True,
        "freeOnly": True,
        "disclosure": AI_DISCLOSURE,
    }


def _voice(value: str | None) -> str:
    voice = str(value or DEFAULT_VOICE).strip().lower()
    voice = LEGACY_VOICE_ALIASES.get(voice, voice)
    return voice if voice in ALLOWED_VOICES else DEFAULT_VOICE


def _preview_identity(voice: str | None) -> tuple[str, str, str]:
    normalized_voice = _voice(voice)
    model = str(os.environ.get("KOKORO_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    identity = {
        "repoId": _repo_id(),
        "model": model,
        "voice": normalized_voice,
        "text": VOICE_PREVIEW_TEXT,
        "speed": f"{_tts_speed():.3f}",
    }
    digest = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:24]
    return normalized_voice, model, f"system/voice-previews/kokoro/{digest}/{normalized_voice}.wav"


def _material_id(job_id: str) -> str:
    digest = hashlib.sha256(str(job_id).encode("utf-8")).hexdigest()[:24]
    return f"mat-ai-audio-{digest}"


def _safe_name(value: str) -> str:
    text = str(value or "AI語音教材").strip().replace("/", "-").replace("\\", "-")
    return " ".join(text.split())[:80] or "AI語音教材"


def _entry(*, job_id: str, script: dict, source: dict, voice: str, model: str, object_key: str, object_bytes: int,
           segments: list[dict] | None = None) -> dict:
    material_id = _material_id(job_id)
    filename = f"{_safe_name(script.get('title') or source.get('title') or 'AI語音教材')}-AI語音.wav"
    stamp = dt.datetime.now(dt.timezone.utc).isoformat()
    source_desc = str(source.get("desc") or "").strip()
    description = "\n".join(filter(None, [source_desc, AI_DISCLOSURE]))[:2000]
    storage_meta = {
        "generated": True,
        "generatedBy": "teacher-ai-worker",
        "mediaKind": "ai_narration",
        "sourceScriptId": str(script.get("id") or ""),
        "sourceMaterialId": str(script.get("materialId") or source.get("id") or ""),
        "teacherApprovedBy": str(script.get("approvedBy") or ""),
        "teacherApprovedAt": str(script.get("approvedAt") or ""),
        "aiGeneratedVoice": True,
        "aiDisclosure": AI_DISCLOSURE,
        "ttsProvider": "kokoro-local",
        "ttsModel": model,
        "ttsVoice": voice,
        "objectBytes": int(object_bytes or 0),
        # Used by the learner player to detect a slide deck that changed after the
        # narration was made (then it plays the voice without per-slide stops).
        "sourceVersion": max(1, int(source.get("currentVersion") or 1)),
    }
    if segments:
        storage_meta["segmented"] = True
        storage_meta["segments"] = [
            {"page": int(item["page"]), "startMs": int(item["startMs"]), "endMs": int(item["endMs"])}
            for item in segments
        ]
        storage_meta["durationMs"] = int(segments[-1]["endMs"])
    return {
        "id": material_id,
        "filename": filename,
        "title": f"{_safe_name(script.get('title') or source.get('title') or '教學講稿')}｜AI 語音",
        "description": description,
        "category": str(source.get("category") or ""),
        "group_key": str(script.get("group") or source.get("group") or ""),
        "training_area": str(script.get("area") or source.get("area") or "internal"),
        "course_id": str(source.get("courseId") or ""),
        "folder": "",
        "page_count": 0,
        "date_added": stamp,
        "storage_filename": filename,
        "storage_backend": "r2",
        "storage_key": object_key,
        "slides_prefix": "",
        "storage_meta": json.dumps(storage_meta, ensure_ascii=False, separators=(",", ":")),
        "material_type": "standard",
        "atlas_meta": "{}",
        "active": True,
    }


def _insert_material_if_missing(entry: dict) -> dict:
    existing = material_repository.get_material(entry["id"])
    if existing:
        return existing
    material_repository.insert_material(entry, ignore_conflict=True)
    return material_repository.get_material(entry["id"]) or material_repository.material_row_to_dict(entry)


def _existing_r2(client, key: str) -> int:
    try:
        result = client.head_object(Bucket=providers.R2_BUCKET_NAME, Key=key)
        return max(0, int(result.get("ContentLength") or 0))
    except Exception as exc:
        response = getattr(exc, "response", {}) or {}
        status = int(((response.get("ResponseMetadata") or {}).get("HTTPStatusCode") or 0))
        code = str((response.get("Error") or {}).get("Code") or "")
        if status == 404 or code in {"404", "NoSuchKey", "NotFound"}:
            return 0
        raise


def _tensor_to_numpy(audio):
    value = audio
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    return value


def _max_chars() -> int:
    return max(1000, min(50000, int(os.environ.get("KOKORO_TTS_MAX_CHARS", "12000") or 12000)))


def _segment_plan(script: dict, source: dict) -> list[str] | None:
    """Per-slide paragraphs when the script lines up one-to-one with the slides.

    The script generator is told "paragraph k = slide k".  Only when the number
    of paragraphs equals the material's page count is the narration split per
    slide; otherwise (hand-edited script, non-slide material, AI miscount) the
    narration stays one continuous track exactly as before.
    """
    segments = tts_text.split_script_segments(str(script.get("body") or ""))
    try:
        page_count = int(source.get("pageCount") or 0)
    except (TypeError, ValueError):
        page_count = 0
    if page_count >= 1 and len(segments) == page_count and any(segments):
        return segments
    return None


def _segment_note(script: dict, source: dict) -> str:
    """Why the narration is one continuous track (empty when it was split per slide)."""
    segments = tts_text.split_script_segments(str(script.get("body") or ""))
    try:
        page_count = int(source.get("pageCount") or 0)
    except (TypeError, ValueError):
        page_count = 0
    if page_count >= 1 and segments and len(segments) != page_count:
        return f"講稿有 {len(segments)} 段、教材有 {page_count} 張，數量不同，語音維持整段播放（不會逐張停住）。"
    if page_count < 1:
        return "來源教材不是投影片或頁數未知，語音維持整段播放。"
    return ""


def build_segmented_wav(
    texts: list[str],
    synthesize: Callable[[str], bytes],
    *,
    gap_ms: int = SEGMENT_GAP_MS,
    progress: Callable[[int, int], None] | None = None,
) -> tuple[bytes, list[dict[str, int]]]:
    """Synthesize each paragraph and join them into one WAV plus a slide timeline.

    Returns ``(wav_bytes, segments)`` where ``segments`` is
    ``[{"page": 0, "startMs": 0, "endMs": 8200}, ...]`` (0-based page, speech only,
    without the silence gap).  Empty paragraphs keep their page with start == end.
    """
    params: tuple[int, int, int] | None = None
    frames = bytearray()
    segments: list[dict[str, int]] = []
    for index, text in enumerate(texts):
        if progress:
            progress(index, len(texts))
        rate = params[2] if params else DEFAULT_SAMPLE_RATE
        cursor_ms = round(len(frames) / (params[0] * params[1]) / rate * 1000) if params else 0
        if not str(text or "").strip():
            segments.append({"page": index, "startMs": cursor_ms, "endMs": cursor_ms})
            continue
        with wave.open(io.BytesIO(synthesize(text)), "rb") as piece:
            piece_params = (piece.getnchannels(), piece.getsampwidth(), piece.getframerate())
            piece_frames = piece.readframes(piece.getnframes())
        if params is None:
            params = piece_params
        elif piece_params != params:
            raise RuntimeError("各張投影片的語音格式不一致，無法合併。")
        channels, width, rate = params
        bytes_per_second = channels * width * rate
        if frames and gap_ms > 0:
            gap_frames = int(rate * gap_ms / 1000)
            frames.extend(b"\x00" * (gap_frames * channels * width))
        start_ms = round(len(frames) / bytes_per_second * 1000)
        frames.extend(piece_frames)
        end_ms = round(len(frames) / bytes_per_second * 1000)
        segments.append({"page": index, "startMs": start_ms, "endMs": end_ms})
    if params is None:
        raise RuntimeError("講稿沒有可朗讀的內容。")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(params[0])
        wav.setsampwidth(params[1])
        wav.setframerate(params[2])
        wav.writeframes(bytes(frames))
    return buffer.getvalue(), segments


def _synthesize_segmented(
    texts: list[str], *, voice: str, instructions: str, progress_callback=None
) -> tuple[bytes, str, list[dict[str, int]]]:
    spoken = [tts_text.apply_pronunciation(text) for text in texts]
    total = sum(len(text) for text in spoken)
    if total > _max_chars():
        raise RuntimeError(
            f"已核准講稿共 {total} 字，超過目前本機語音單次上限 {_max_chars()} 字；請先縮短或拆成兩份講稿。"
        )
    model_holder: dict[str, str] = {}

    def synth(text: str) -> bytes:
        audio, model = _synthesize(text, voice=voice, instructions=instructions)
        model_holder["model"] = model
        return audio

    def progress(done: int, count: int) -> None:
        if progress_callback:
            progress_callback(
                30 + int(40 * done / max(1, count)),
                "逐張產生 AI 語音",
                f"本機 AI Worker 正在合成第 {done + 1} / {count} 張投影片的講解；沒改過的段落會直接使用快取",
            )

    audio, segments = build_segmented_wav(spoken, synth, progress=progress)
    return audio, model_holder.get("model") or DEFAULT_MODEL, segments


def _synthesize(text: str, *, voice: str, instructions: str) -> tuple[bytes, str]:
    del instructions  # Kokoro currently uses the approved text + configured speed/voice only.
    # Normalize again at the lowest boundary so stale jobs/env cannot reach
    # KPipeline with a removed v1.0 voice name.
    voice = _voice(voice)

    max_chars = _max_chars()
    if len(text) > max_chars:
        raise RuntimeError(
            f"已核准講稿共 {len(text)} 字，超過目前本機語音單次上限 {max_chars} 字；請先縮短或拆成兩份講稿。"
        )
    repo_id = _repo_id()
    model_label = str(os.environ.get("KOKORO_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    if model_label == "Kokoro-82M":
        model_label = DEFAULT_MODEL
    speed = _tts_speed()
    normalized = _normalized_text(text)
    cache_root = _tts_cache_root()
    cache_path = cache_root / f"{tts_cache_key(normalized, repo_id=repo_id, voice=voice, speed=speed)}.wav"
    _clean_tts_cache(cache_root)
    try:
        if cache_path.is_file() and cache_path.stat().st_size >= 1024:
            return cache_path.read_bytes(), model_label
    except OSError:
        pass

    # Cache hits must not require NumPy/Kokoro to be imported. This keeps
    # previews and unchanged slide narration lightweight and lets generic Web
    # regression environments exercise the cache path without AI dependencies.
    try:
        import numpy as np
    except Exception as exc:
        raise RuntimeError(
            "本機免費語音尚未安裝完成；請在 AI Worker 執行 requirements-ai-worker.txt。"
        ) from exc

    def _synthesize_waveform():
        pipeline = _kokoro_pipeline(repo_id)
        chunks = []
        for result in pipeline(normalized, voice=voice, speed=speed, split_pattern=r"\n+"):
            audio = getattr(result, "audio", None)
            if audio is None and isinstance(result, (tuple, list)) and len(result) >= 3:
                audio = result[2]
            if audio is None:
                continue
            chunk = np.asarray(_tensor_to_numpy(audio), dtype=np.float32).reshape(-1)
            if chunk.size:
                chunks.append(chunk)
        if not chunks:
            raise RuntimeError("Kokoro 沒有產生有效音訊。")
        return np.concatenate(chunks)

    try:
        try:
            waveform = _synthesize_waveform()
        except Exception:
            # Auto offline mode only skips network checks for cached assets.  A
            # voice that is not cached yet needs one download, so re-enable the
            # network once and retry before reporting a failure.
            if not _disable_auto_hf_offline():
                raise
            waveform = _synthesize_waveform()
    except Exception as exc:
        message = str(exc)
        if "Entry Not Found" in message or "404 Client Error" in message or "/voices/" in message:
            raise RuntimeError(
                f"Kokoro 音色檔不存在（repo={repo_id}, voice={voice}）；"
                "目前只使用 v1.1-zh 編號式中文音色。"
                "若錯誤仍顯示 zf_xiaoni/zf_xiaoxiao，代表院內 AI Worker 仍在執行舊版程式；"
                "請更新 main 後重新啟動 Teacher AI Worker。"
            ) from exc
        if isinstance(exc, RuntimeError):
            raise
        raise RuntimeError("本機 Kokoro 語音產生失敗；詳細錯誤已寫入 AI Worker log。") from exc

    pcm = (np.clip(waveform, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(DEFAULT_SAMPLE_RATE)
        wav.writeframes(pcm)
    audio_bytes = buffer.getvalue()
    if len(audio_bytes) < 1024:
        raise RuntimeError("本機 Kokoro 沒有回傳有效音訊。")
    try:
        cache_root.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_name(f"{cache_path.name}.{os.getpid()}.tmp")
        temporary.write_bytes(audio_bytes)
        os.replace(temporary, cache_path)
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except (OSError, UnboundLocalError):
            pass
    return audio_bytes, model_label


def generate_voice_preview(*, job_id: str, voice: str, progress_callback=None) -> dict:
    """Generate/cache a short non-material preview using the same local Kokoro voice."""
    if not providers.r2_is_configured():
        raise RuntimeError("Cloudflare R2 尚未完成設定，無法提供 AI 語音試聽。")
    if _provider() != DEFAULT_PROVIDER:
        raise RuntimeError("目前只允許免費本機 Kokoro 語音。")
    voice, model, object_key = _preview_identity(voice)
    client = providers.r2_client()

    if progress_callback:
        progress_callback(15, "檢查語音試聽", "確認這個聲音是否已有快取試聽")
    existing_bytes = _existing_r2(client, object_key)
    if existing_bytes > 0:
        r2_ledger.record_object(object_key, existing_bytes, estimated_operations=1, is_staging=False)
        return {
            "preview": True,
            "previewObjectKey": object_key,
            "voice": voice,
            "model": model,
            "replayed": True,
            "mimeType": "audio/wav",
        }

    if progress_callback:
        progress_callback(40, "產生語音試聽", "AI Worker 正在產生短版中文試聽")
    audio, model = _synthesize(VOICE_PREVIEW_TEXT, voice=voice, instructions="")
    if progress_callback:
        progress_callback(75, "保存語音試聽", "正在保存短版試聽快取")
    r2_budget.reserve_upload(job_id, object_key, len(audio))
    try:
        client.put_object(
            Bucket=providers.R2_BUCKET_NAME,
            Key=object_key,
            Body=audio,
            ContentType="audio/wav",
            CacheControl="private, max-age=86400",
            Metadata={
                "ai-generated": "true",
                "voice-preview": "true",
                "tts-provider": "kokoro-local",
            },
        )
        r2_ledger.record_object(object_key, len(audio), estimated_operations=1, is_staging=False)
        r2_budget.release_reservation(job_id, "published")
    except Exception:
        r2_budget.release_reservation(job_id, "failed")
        raise
    if progress_callback:
        progress_callback(95, "語音試聽完成", "短版試聽已快取，可直接播放")
    return {
        "preview": True,
        "previewObjectKey": object_key,
        "voice": voice,
        "model": model,
        "replayed": False,
        "mimeType": "audio/wav",
    }


def cached_voice_preview(voice: str | None) -> dict:
    """Return a ready cached preview without waiting for the local Worker."""
    if not configured():
        return {}
    normalized_voice, model, object_key = _preview_identity(voice)
    try:
        existing_bytes = _existing_r2(providers.r2_client(), object_key)
        if existing_bytes <= 0:
            return {}
        r2_ledger.record_object(object_key, existing_bytes, estimated_operations=1, is_staging=False)
        url = preview_url(object_key)
    except Exception:
        return {}
    if not url:
        return {}
    return {
        "preview": True,
        "previewUrl": url,
        "voice": normalized_voice,
        "model": model,
        "replayed": True,
        "mimeType": "audio/wav",
    }


def preview_url(object_key: str) -> str:
    key = str(object_key or "").strip()
    if not key.startswith("system/voice-previews/kokoro/"):
        return ""
    return providers.r2_client().generate_presigned_url(
        "get_object",
        Params={
            "Bucket": providers.R2_BUCKET_NAME,
            "Key": key,
            "ResponseContentType": "audio/wav",
            "ResponseContentDisposition": 'inline; filename="voice-preview.wav"',
        },
        ExpiresIn=min(3600, int(providers.R2_PRESIGN_SECONDS)),
    )


def generate_audio(*, job_id: str, script: dict, source: dict, voice: str, instructions: str = "", progress_callback=None) -> dict:
    if str(script.get("status") or "") != "approved":
        raise RuntimeError("只有已由授課教師核准的講稿可以產生 AI 語音。")
    if not str(script.get("approvedBy") or "").strip() or not str(script.get("approvedAt") or "").strip():
        raise RuntimeError("講稿缺少教師核准紀錄，不能產生 AI 語音。")
    if not providers.r2_is_configured():
        raise RuntimeError("Cloudflare R2 尚未完成設定，無法保存 AI 語音教材。")
    if _provider() != DEFAULT_PROVIDER:
        raise RuntimeError("目前只允許免費本機 Kokoro 語音。")

    voice = _voice(voice)
    material_id = _material_id(job_id)
    existing_material = material_repository.get_material(material_id)
    if existing_material:
        return {
            "materialId": material_id,
            "material": existing_material,
            "voice": voice,
            "model": str((existing_material.get("storageMeta") or {}).get("ttsModel") or ""),
            "disclosure": AI_DISCLOSURE,
            "replayed": True,
        }

    filename = f"{_safe_name(script.get('title') or source.get('title') or 'AI語音教材')}-AI語音.wav"
    object_key = f"materials/{material_id}/{filename}"
    client = providers.r2_client()

    if progress_callback:
        progress_callback(10, "檢查既有輸出", "確認是否已有相同工作產生的 R2 音訊")
    existing_bytes = _existing_r2(client, object_key)
    if existing_bytes > 0:
        model = str(os.environ.get("KOKORO_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL
        entry = _entry(
            job_id=job_id, script=script, source=source, voice=voice, model=model,
            object_key=object_key, object_bytes=existing_bytes,
        )
        r2_ledger.record_object(object_key, existing_bytes, estimated_operations=1, is_staging=False)
        material = _insert_material_if_missing(entry)
        return {
            "materialId": material_id, "material": material, "voice": voice, "model": model,
            "disclosure": AI_DISCLOSURE, "replayed": True,
        }

    plan = _segment_plan(script, source)
    segments: list[dict[str, int]] = []
    if plan:
        audio, model, segments = _synthesize_segmented(
            plan, voice=voice, instructions=instructions, progress_callback=progress_callback
        )
    else:
        if progress_callback:
            progress_callback(30, "產生免費 AI 語音", "本機 AI Worker 正在使用 Kokoro 將已核准講稿轉成 WAV")
        spoken = tts_text.apply_pronunciation(str(script.get("body") or "").strip())
        audio, model = _synthesize(spoken, voice=voice, instructions=instructions)

    if progress_callback:
        progress_callback(70, "保存 AI 語音", "正在將 WAV 直接寫入 Cloudflare R2")
    r2_budget.reserve_upload(job_id, object_key, len(audio))
    try:
        client.put_object(
            Bucket=providers.R2_BUCKET_NAME,
            Key=object_key,
            Body=audio,
            ContentType="audio/wav",
            Metadata={
                "teacher-script-id": str(script.get("id") or "")[:200],
                "ai-generated": "true",
                "tts-provider": "kokoro-local",
            },
        )
        r2_ledger.record_object(object_key, len(audio), estimated_operations=1, is_staging=False)
        entry = _entry(
            job_id=job_id, script=script, source=source, voice=voice, model=model,
            object_key=object_key, object_bytes=len(audio), segments=segments,
        )
        material = _insert_material_if_missing(entry)
        r2_budget.release_reservation(job_id, "published")
    except Exception:
        r2_budget.release_reservation(job_id, "failed")
        raise

    if progress_callback:
        progress_callback(95, "建立語音教材", "免費本機 AI 語音已保存並加入原課程教材")
    return {
        "materialId": material_id,
        "material": material,
        "voice": voice,
        "model": model,
        "disclosure": AI_DISCLOSURE,
        "replayed": False,
        "segmented": bool(segments),
        "segmentCount": len(segments),
        "segmentNote": "" if segments else _segment_note(script, source),
    }


__all__ = [
    "AI_DISCLOSURE",
    "ALLOWED_VOICES",
    "VOICE_PREVIEW_TEXT",
    "build_segmented_wav",
    "configured",
    "generate_audio",
    "generate_voice_preview",
    "cached_voice_preview",
    "preview_url",
    "preload_kokoro",
    "public_status",
    "tts_cache_key",
]
