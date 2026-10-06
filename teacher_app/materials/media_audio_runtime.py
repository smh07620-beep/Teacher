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
import threading
import wave
from typing import Any

from teacher_app.materials import repository as material_repository
from teacher_app.storage import providers, r2_budget, r2_ledger


AI_DISCLOSURE = "本音訊為本機 AI 合成語音，內容來源為授課教師已核准之教學講稿。"
VOICE_PREVIEW_TEXT = "您好，這是醫學檢驗教學平台的 AI 語音試聽。"
DEFAULT_PROVIDER = "kokoro"
DEFAULT_MODEL = "Kokoro-82M-v1.1-zh"
DEFAULT_REPO_ID = "hexgrad/Kokoro-82M-v1.1-zh"
DEFAULT_VOICE = "zf_001"
DEFAULT_SAMPLE_RATE = 24000
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


def _kokoro_pipeline(repo_id: str):
    """Lazily load Kokoro once per Worker process instead of once per preview/job."""
    global _KOKORO_PIPELINE, _KOKORO_PIPELINE_KEY
    key = f"z::{repo_id}"
    if _KOKORO_PIPELINE is not None and _KOKORO_PIPELINE_KEY == key:
        return _KOKORO_PIPELINE
    with _KOKORO_PIPELINE_LOCK:
        if _KOKORO_PIPELINE is not None and _KOKORO_PIPELINE_KEY == key:
            return _KOKORO_PIPELINE
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
    model_key = hashlib.sha256(model.encode("utf-8")).hexdigest()[:10]
    return normalized_voice, model, f"system/voice-previews/kokoro/{model_key}/{normalized_voice}.wav"


def _material_id(job_id: str) -> str:
    digest = hashlib.sha256(str(job_id).encode("utf-8")).hexdigest()[:24]
    return f"mat-ai-audio-{digest}"


def _safe_name(value: str) -> str:
    text = str(value or "AI語音教材").strip().replace("/", "-").replace("\\", "-")
    return " ".join(text.split())[:80] or "AI語音教材"


def _entry(*, job_id: str, script: dict, source: dict, voice: str, model: str, object_key: str, object_bytes: int) -> dict:
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
    }
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


def _synthesize(text: str, *, voice: str, instructions: str) -> tuple[bytes, str]:
    del instructions  # Kokoro currently uses the approved text + configured speed/voice only.
    try:
        import numpy as np
    except Exception as exc:
        raise RuntimeError(
            "本機免費語音尚未安裝完成；請在 AI Worker 執行 requirements-ai-worker.txt。"
        ) from exc

    max_chars = max(1000, min(50000, int(os.environ.get("KOKORO_TTS_MAX_CHARS", "12000") or 12000)))
    if len(text) > max_chars:
        raise RuntimeError(
            f"已核准講稿共 {len(text)} 字，超過目前本機語音單次上限 {max_chars} 字；請先縮短或拆成兩份講稿。"
        )
    repo_id = str(os.environ.get("KOKORO_REPO_ID") or DEFAULT_REPO_ID).strip() or DEFAULT_REPO_ID
    model_label = str(os.environ.get("KOKORO_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    try:
        speed = float(os.environ.get("KOKORO_TTS_SPEED", "1.0") or 1.0)
    except (TypeError, ValueError):
        speed = 1.0
    speed = max(0.75, min(1.35, speed))

    try:
        pipeline = _kokoro_pipeline(repo_id)
        chunks = []
        for result in pipeline(text, voice=voice, speed=speed, split_pattern=r"\n+"):
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
        waveform = np.concatenate(chunks)
    except Exception as exc:
        message = str(exc)
        if "Entry Not Found" in message or "404 Client Error" in message or "/voices/" in message:
            raise RuntimeError(
                "Kokoro 音色檔不存在；目前使用 v1.1-zh 編號式中文音色。"
                "請重新載入頁面；若院內 Worker 尚未更新，請更新 main 後重新啟動。"
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

    if progress_callback:
        progress_callback(30, "產生免費 AI 語音", "本機 AI Worker 正在使用 Kokoro 將已核准講稿轉成 WAV")
    audio, model = _synthesize(str(script.get("body") or "").strip(), voice=voice, instructions=instructions)

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
            object_key=object_key, object_bytes=len(audio),
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
    }


__all__ = [
    "AI_DISCLOSURE",
    "ALLOWED_VOICES",
    "VOICE_PREVIEW_TEXT",
    "configured",
    "generate_audio",
    "generate_voice_preview",
    "cached_voice_preview",
    "preview_url",
    "public_status",
]
