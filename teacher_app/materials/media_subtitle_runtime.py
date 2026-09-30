"""AI subtitle transcription runtime executed only by the dedicated AI Worker."""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlparse

import requests

from teacher_app.assessments import ai_runtime, free_ai_fallback
from teacher_app.common import privacy as ai_privacy
from teacher_app.config import external_media_hospital_cdn_hosts, storage_paths
from teacher_app.materials import external_media, repository as material_repository


_LOCAL_WHISPER_CACHE: dict[tuple[str, str, str], object] = {}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _timestamp(seconds: float, *, srt: bool = False) -> str:
    milliseconds = max(0, int(round(float(seconds or 0) * 1000)))
    hours, rem = divmod(milliseconds, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    separator = "," if srt else "."
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis:03d}"


def segments_to_vtt(segments: list[dict]) -> str:
    lines = ["WEBVTT", ""]
    cue = 0
    for segment in segments:
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        start = max(0.0, float(segment.get("start") or 0.0))
        end = max(start + 0.2, float(segment.get("end") or 0.0))
        cue += 1
        lines.extend([str(cue), f"{_timestamp(start)} --> {_timestamp(end)}", text, ""])
    if cue == 0:
        raise RuntimeError("AI 沒有辨識到可用字幕內容。")
    return "\n".join(lines).strip() + "\n"


def segments_to_srt(segments: list[dict]) -> str:
    lines: list[str] = []
    cue = 0
    for segment in segments:
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        start = max(0.0, float(segment.get("start") or 0.0))
        end = max(start + 0.2, float(segment.get("end") or 0.0))
        cue += 1
        lines.extend([str(cue), f"{_timestamp(start, srt=True)} --> {_timestamp(end, srt=True)}", text, ""])
    return "\n".join(lines).strip() + ("\n" if lines else "")


def normalize_vtt(value: str) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff").strip()
    if len(text.encode("utf-8")) > 2 * 1024 * 1024:
        raise ValueError("字幕內容超過 2 MiB 限制。")
    if not text.startswith("WEBVTT"):
        raise ValueError("字幕必須是 WebVTT（第一行需為 WEBVTT）。")
    if "-->" not in text:
        raise ValueError("WebVTT 內容至少需要一個時間軸 cue。")
    return text + "\n"


def vtt_to_srt(vtt_text: str) -> str:
    text = normalize_vtt(vtt_text)
    blocks = re.split(r"\n\s*\n", text[len("WEBVTT"):].strip())
    output: list[str] = []
    index = 0
    for block in blocks:
        lines = [line.strip("\ufeff") for line in block.splitlines() if line.strip()]
        if not lines or lines[0].startswith(("NOTE", "STYLE", "REGION")):
            continue
        timing_index = next((i for i, line in enumerate(lines) if "-->" in line), -1)
        if timing_index < 0:
            continue
        timing = lines[timing_index].replace(".", ",")
        body = lines[timing_index + 1:]
        if not body:
            continue
        index += 1
        output.extend([str(index), timing, *body, ""])
    return "\n".join(output).strip() + ("\n" if output else "")


def _groq_error(response) -> str:
    try:
        data = response.json()
        error = data.get("error") if isinstance(data, dict) else None
        if isinstance(error, dict):
            return str(error.get("message") or error)[:500]
        return str(error or data)[:500]
    except Exception:
        return str(getattr(response, "text", "") or "")[:500]


def groq_transcribe_segments(path: Path, *, settings=None) -> list[dict]:
    settings = settings or ai_runtime.ai_settings()
    if not settings.groq_api_key:
        raise RuntimeError("Groq 尚未設定 GROQ_API_KEY。")
    with Path(path).open("rb") as handle:
        response = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            files={"file": (Path(path).name, handle, "application/octet-stream")},
            data={
                "model": settings.groq_transcribe_model,
                "response_format": "verbose_json",
                "timestamp_granularities[]": "segment",
            },
            timeout=180,
        )
    if response.status_code == 429:
        raise RuntimeError("Groq 免費 AI 額度/速率已達上限，請稍後再試。")
    if response.status_code >= 500:
        raise RuntimeError(f"Groq transcription provider unavailable HTTP {response.status_code}。")
    if response.status_code >= 400:
        raise RuntimeError(f"Groq 語音轉文字失敗 HTTP {response.status_code}：{_groq_error(response)}")
    try:
        data = response.json()
    except Exception as exc:
        raise RuntimeError("Groq 語音轉文字回傳格式無法解析。") from exc
    raw_segments = data.get("segments") if isinstance(data, dict) else None
    if not isinstance(raw_segments, list) or not raw_segments:
        raise RuntimeError("Groq 語音轉文字未回傳可用時間軸 segments。")
    segments: list[dict] = []
    for item in raw_segments:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        start = float(item.get("start") or 0.0)
        end = float(item.get("end") or 0.0)
        segments.append({"start": start, "end": max(end, start + 0.2), "text": text})
    if not segments:
        raise RuntimeError("Groq 語音轉文字未辨識到可用字幕。")
    return segments


def local_transcribe_segments(path: Path, *, local=None) -> list[dict]:
    local = local or free_ai_fallback.LocalFallbackSettings.from_env()
    if not local.whisper_enabled:
        raise RuntimeError("本機 Whisper 字幕備援尚未啟用。")
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("本機 faster-whisper 尚未安裝。") from exc
    key = (local.whisper_model, local.whisper_device, local.whisper_compute_type)
    model = _LOCAL_WHISPER_CACHE.get(key)
    if model is None:
        model = WhisperModel(local.whisper_model, device=local.whisper_device, compute_type=local.whisper_compute_type)
        _LOCAL_WHISPER_CACHE[key] = model
    raw_segments, _info = model.transcribe(str(path), vad_filter=True)
    segments: list[dict] = []
    for item in raw_segments:
        text = str(getattr(item, "text", "") or "").strip()
        if not text:
            continue
        start = float(getattr(item, "start", 0.0) or 0.0)
        end = float(getattr(item, "end", 0.0) or 0.0)
        segments.append({"start": start, "end": max(end, start + 0.2), "text": text})
    if not segments:
        raise RuntimeError("本機 Whisper 沒有辨識到可用字幕。")
    return segments


def transcribe_segments(path: Path, *, settings=None, local=None) -> tuple[list[dict], dict]:
    settings = settings or ai_runtime.ai_settings()
    local = local or free_ai_fallback.LocalFallbackSettings.from_env()
    cloud_allowed = bool(
        ai_privacy.external_enabled()
        and ai_privacy.external_media_allowed()
        and settings.groq_api_key
    )
    attempted_cloud = False
    if cloud_allowed:
        attempted_cloud = True
        try:
            return groq_transcribe_segments(path, settings=settings), {
                "provider": "groq",
                "model": settings.groq_transcribe_model,
                "fallbackUsed": False,
            }
        except Exception as exc:
            if not free_ai_fallback.is_retryable_provider_error(exc):
                raise
            if not local.whisper_enabled:
                raise
    if local.whisper_enabled:
        return local_transcribe_segments(path, local=local), {
            "provider": "local-whisper",
            "model": local.whisper_model,
            "fallbackUsed": attempted_cloud,
        }
    if not ai_privacy.external_media_allowed():
        raise RuntimeError(
            "院方目前禁止將影音送往外部 AI，且本機 Whisper 尚未啟用；請在 AI Worker 啟用 LOCAL_WHISPER_ENABLED。"
        )
    raise RuntimeError("AI 字幕服務尚未完成設定；請設定 Groq Whisper 或本機 faster-whisper。")


def _download_direct_external(material: dict, *, settings) -> tuple[Path, Path, str]:
    media = external_media.get_external_media(str(material.get("id") or "")) or {}
    provider = str(media.get("provider") or "").lower()
    if provider in {"youtube", "vimeo"}:
        raise RuntimeError(
            "YouTube/Vimeo 為平台 iframe 掛載，Teacher 不會繞過平台下載原始影音；無法自動產生自有字幕。"
        )
    if provider != "direct":
        raise RuntimeError("此外部影音沒有可由 AI Worker 安全存取的原始媒體來源。")
    validated = external_media.validate_external_url(
        str(media.get("canonicalUrl") or ""),
        external_media_hospital_cdn_hosts(),
    )
    if validated.get("provider") != "direct":
        raise RuntimeError("外部影音不是允許的 hospital CDN direct video。")
    url = str(validated.get("canonicalUrl") or "")
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix.lower()
    if suffix not in {".mp4", ".webm"}:
        raise RuntimeError("外部 direct video 僅支援 MP4/WebM 字幕轉錄。")
    root = Path(storage_paths().tmp_dir) / f"msub-ext-{uuid.uuid4().hex[:10]}"
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"source{suffix}"
    max_bytes = max(10, int(settings.media_max_mb or 300)) * 1024 * 1024
    try:
        with requests.get(url, stream=True, timeout=(10, 120), allow_redirects=False) as response:
            if 300 <= response.status_code < 400:
                raise RuntimeError("外部 direct video 發生重新導向；為避免 SSRF 不自動跟隨。")
            if response.status_code != 200:
                raise RuntimeError(f"外部 direct video 讀取失敗 HTTP {response.status_code}。")
            length = int(response.headers.get("Content-Length") or 0)
            if length and length > max_bytes:
                raise RuntimeError("外部影音超過 AI_MEDIA_MAX_MB 限制。")
            total = 0
            with target.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > max_bytes:
                        raise RuntimeError("外部影音超過 AI_MEDIA_MAX_MB 限制。")
                    handle.write(chunk)
        if not target.is_file() or target.stat().st_size <= 0:
            raise RuntimeError("外部影音下載內容為空。")
        locator = f"external-direct:{parsed.hostname or ''}{parsed.path}"
        return root, target, locator
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise


def _audio_source(material: dict, *, settings) -> tuple[list[Path], Path, str, str]:
    roots: list[Path] = []
    backend = str(material.get("storageBackend") or "local").lower()
    material_id = str(material.get("id") or "")
    version = max(1, int(material.get("currentVersion") or 1))
    if backend == "external":
        root, video, locator = _download_direct_external(material, settings=settings)
        roots.append(root)
        audio, _frames = ai_runtime.extract_video_audio_and_frames(video, root, settings=settings)
        if audio is None or not Path(audio).is_file():
            raise RuntimeError("外部影片無法抽取音訊供字幕辨識。")
        return roots, Path(audio), "external-direct-video", locator

    kind = ai_runtime.material_kind(material)
    if kind == "video":
        derived_root, derived = ai_runtime.material_derivatives_to_temp(material)
        roots.append(derived_root)
        audio = derived.get("audio.m4a")
        if audio is not None:
            return roots, Path(audio), "uploaded-video-audio-derivative", f"material:{material_id}:v{version}:audio.m4a"
        source_root, source = ai_runtime.material_source_to_temp(material)
        roots.append(source_root)
        audio, _frames = ai_runtime.extract_video_audio_and_frames(source, source_root, settings=settings)
        if audio is None or not Path(audio).is_file():
            raise RuntimeError("上傳影片無法抽取音訊供字幕辨識。")
        return roots, Path(audio), "uploaded-video", f"material:{material_id}:v{version}:source"
    if kind == "audio":
        source_root, source = ai_runtime.material_source_to_temp(material)
        roots.append(source_root)
        return roots, Path(source), "uploaded-audio", f"material:{material_id}:v{version}:source"
    raise RuntimeError("AI 字幕只支援上傳影音或允許的 direct hospital CDN 影片。")


def generate_subtitle(material: dict, *, language: str = "zh-TW", label: str = "繁體中文字幕", progress_callback=None) -> dict:
    if not material or not material.get("id"):
        raise RuntimeError("找不到字幕來源教材。")
    settings = ai_runtime.ai_settings()
    local = free_ai_fallback.LocalFallbackSettings.from_env()
    roots: list[Path] = []
    try:
        if progress_callback:
            progress_callback(10, "準備影音來源", "正在取得可轉錄的音訊來源")
        roots, audio, source_kind, source_locator = _audio_source(material, settings=settings)
        source_sha = _sha256(audio)
        if progress_callback:
            mode = "雲端 Groq Whisper" if ai_privacy.external_media_allowed() and settings.groq_api_key else "本機 faster-whisper"
            progress_callback(35, "AI 語音辨識", f"使用 {mode} 建立時間軸字幕")
        segments, meta = transcribe_segments(audio, settings=settings, local=local)
        if progress_callback:
            progress_callback(80, "建立字幕檔", "正在輸出 WebVTT / SRT 與文字稿")
        vtt = segments_to_vtt(segments)
        srt = segments_to_srt(segments)
        transcript = "\n".join(str(item.get("text") or "").strip() for item in segments if str(item.get("text") or "").strip())
        return {
            "language": str(language or "zh-TW")[:32],
            "label": str(label or "繁體中文字幕")[:80],
            "vttText": vtt,
            "srtText": srt,
            "transcriptText": transcript,
            "provider": meta["provider"],
            "model": meta["model"],
            "fallbackUsed": bool(meta.get("fallbackUsed")),
            "sourceVersion": max(1, int(material.get("currentVersion") or 1)),
            "sourceSha256": source_sha,
            "sourceKind": source_kind,
            "sourceLocator": source_locator,
        }
    finally:
        for root in roots:
            shutil.rmtree(root, ignore_errors=True)


__all__ = [
    "generate_subtitle", "groq_transcribe_segments", "local_transcribe_segments", "normalize_vtt",
    "segments_to_srt", "segments_to_vtt", "transcribe_segments", "vtt_to_srt",
]
