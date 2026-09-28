"""Approved teacher script -> AI narration -> durable R2 material."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import requests

from teacher_app.materials import repository as material_repository
from teacher_app.storage import providers, r2_budget, r2_ledger


AI_DISCLOSURE = "本音訊為 AI 合成語音，內容來源為授課教師已核准之教學講稿。"
DEFAULT_MODEL = "gpt-4o-mini-tts"
DEFAULT_VOICE = "marin"
ALLOWED_VOICES = {
    "alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer",
    "verse", "marin", "cedar",
}


def configured() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY", "").strip() and providers.r2_is_configured())


def public_status() -> dict[str, Any]:
    return {
        "enabled": configured(),
        "provider": "openai" if os.environ.get("OPENAI_API_KEY", "").strip() else "",
        "model": os.environ.get("OPENAI_TTS_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        "defaultVoice": _voice(os.environ.get("OPENAI_TTS_VOICE", DEFAULT_VOICE)),
        "voices": sorted(ALLOWED_VOICES),
        "requiresApprovedScript": True,
        "storesToR2": True,
        "disclosure": AI_DISCLOSURE,
    }


def _voice(value: str | None) -> str:
    voice = str(value or DEFAULT_VOICE).strip().lower()
    return voice if voice in ALLOWED_VOICES else DEFAULT_VOICE


def _material_id(job_id: str) -> str:
    digest = hashlib.sha256(str(job_id).encode("utf-8")).hexdigest()[:24]
    return f"mat-ai-audio-{digest}"


def _safe_name(value: str) -> str:
    text = str(value or "AI語音教材").strip().replace("/", "-").replace("\\", "-")
    return " ".join(text.split())[:80] or "AI語音教材"


def _entry(*, job_id: str, script: dict, source: dict, voice: str, model: str, object_key: str, object_bytes: int) -> dict:
    material_id = _material_id(job_id)
    filename = f"{_safe_name(script.get('title') or source.get('title') or 'AI語音教材')}-AI語音.mp3"
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
        "ttsProvider": "openai",
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


def _synthesize(text: str, *, voice: str, instructions: str) -> tuple[bytes, str]:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("AI 語音尚未設定 OPENAI_API_KEY。")
    model = os.environ.get("OPENAI_TTS_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    # Keep one approved script as one speech request so output remains one
    # coherent MP3 and does not require FFmpeg in the lightweight AI worker.
    max_chars = max(1000, min(50000, int(os.environ.get("OPENAI_TTS_MAX_CHARS", "12000") or 12000)))
    if len(text) > max_chars:
        raise RuntimeError(
            f"已核准講稿共 {len(text)} 字，超過目前 AI 語音單次上限 {max_chars} 字；請先縮短或拆成兩份講稿。"
        )
    response = requests.post(
        "https://api.openai.com/v1/audio/speech",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "voice": voice,
            "input": text,
            "instructions": instructions,
            "response_format": "mp3",
        },
        timeout=300,
    )
    if response.status_code == 429:
        raise RuntimeError("AI 語音服務目前已達速率或額度上限，請稍後再試。")
    if not response.ok:
        try:
            detail = str((response.json() or {}).get("error", {}).get("message") or "")
        except Exception:
            detail = ""
        raise RuntimeError(f"AI 語音產生失敗（HTTP {response.status_code}）{('：' + detail[:300]) if detail else ''}")
    audio = bytes(response.content or b"")
    if len(audio) < 1024:
        raise RuntimeError("AI 語音服務沒有回傳有效音訊。")
    return audio, model


def generate_audio(*, job_id: str, script: dict, source: dict, voice: str, instructions: str = "", progress_callback=None) -> dict:
    if str(script.get("status") or "") != "approved":
        raise RuntimeError("只有已由授課教師核准的講稿可以產生 AI 語音。")
    if not str(script.get("approvedBy") or "").strip() or not str(script.get("approvedAt") or "").strip():
        raise RuntimeError("講稿缺少教師核准紀錄，不能產生 AI 語音。")
    if not providers.r2_is_configured():
        raise RuntimeError("Cloudflare R2 尚未完成設定，無法保存 AI 語音教材。")

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

    filename = f"{_safe_name(script.get('title') or source.get('title') or 'AI語音教材')}-AI語音.mp3"
    object_key = f"materials/{material_id}/{filename}"
    client = providers.r2_client()

    if progress_callback:
        progress_callback(10, "檢查既有輸出", "確認是否已有相同工作產生的 R2 音訊")
    existing_bytes = _existing_r2(client, object_key)
    if existing_bytes > 0:
        model = os.environ.get("OPENAI_TTS_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
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
        progress_callback(30, "產生 AI 語音", "正在將已核准講稿轉成 MP3；此語音會標示為 AI 生成")
    spoken_instructions = str(instructions or "").strip()[:500] or (
        "Speak clearly and professionally in Traditional Chinese, at a calm teaching pace. "
        "Preserve medical terms, numbers, units, and abbreviations exactly as written."
    )
    audio, model = _synthesize(str(script.get("body") or "").strip(), voice=voice, instructions=spoken_instructions)

    if progress_callback:
        progress_callback(70, "保存 AI 語音", "正在將 MP3 直接寫入 Cloudflare R2")
    r2_budget.reserve_upload(job_id, object_key, len(audio))
    try:
        client.put_object(
            Bucket=providers.R2_BUCKET_NAME,
            Key=object_key,
            Body=audio,
            ContentType="audio/mpeg",
            Metadata={
                "teacher-script-id": str(script.get("id") or "")[:200],
                "ai-generated": "true",
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
        progress_callback(95, "建立語音教材", "AI 語音已保存並加入原課程教材")
    return {
        "materialId": material_id,
        "material": material,
        "voice": voice,
        "model": model,
        "disclosure": AI_DISCLOSURE,
        "replayed": False,
    }


__all__ = ["AI_DISCLOSURE", "ALLOWED_VOICES", "configured", "generate_audio", "public_status"]
