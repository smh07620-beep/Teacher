"""Worker-only presentation revision -> local TTS -> captions/timeline -> FFmpeg MP4."""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any, Callable, Mapping

from teacher_app.materials import ai_presentation_repository as presentation_repository
from teacher_app.materials import ai_video_repository as repository
from teacher_app.materials.ai_video_storage import VideoStorage
from teacher_app.materials.media_audio_runtime import DEFAULT_MODEL, DEFAULT_PROVIDER, _synthesize, _voice
from teacher_app.materials.media_subtitle_runtime import segments_to_srt, segments_to_vtt


def _safe_text(value: Any, limit=4000) -> str:
    text = " ".join(str(value or "").replace("\x00", " ").split())[:limit]
    lowered = text.lower()
    if any(marker in lowered for marker in ("token=", "password=", "secret=", "api_key=", "authorization:", "bearer ")) or "/home/" in lowered or "\\users\\" in lowered:
        raise ValueError("影片 provenance 或講稿含有不允許的敏感資訊或本機路徑。")
    return text


def narration_for_slide(slide: Mapping[str, Any]) -> str:
    notes = _safe_text(slide.get("speakerNotes"), 4000)
    if notes: return notes
    title = _safe_text(slide.get("title"), 300)
    bullets = [_safe_text(item, 700) for item in list(slide.get("bullets") or [])[:8]]
    return "。".join(part for part in [title, *bullets] if part) or "本頁投影片內容。"


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as source:
        frames, rate = source.getnframes(), source.getframerate()
    return max(0.2, float(frames) / max(1, rate))


def _write_slide_image(path: Path, slide: Mapping[str, Any]) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise RuntimeError("AI Worker 缺少 python-pptx 所需的 Pillow，無法建立影片投影片影格。") from exc
    image = Image.new("RGB", (1280, 720), "#0f172a"); draw = ImageDraw.Draw(image)
    font_path = "C:/Windows/Fonts/msjh.ttc" if Path("C:/Windows/Fonts/msjh.ttc").is_file() else None
    try: title_font = ImageFont.truetype(font_path, 46) if font_path else ImageFont.load_default(); body_font = ImageFont.truetype(font_path, 28) if font_path else ImageFont.load_default()
    except Exception: title_font = body_font = ImageFont.load_default()
    draw.text((70, 70), _safe_text(slide.get("title"), 180), fill="white", font=title_font)
    y = 180
    for bullet in list(slide.get("bullets") or [])[:8]:
        for line in _safe_text(bullet, 500).split("\n"):
            draw.text((100, y), "• " + line, fill="#dbeafe", font=body_font); y += 48
    image.save(path, "PNG")


def _run(command: list[str], *, timeout: int, message: str) -> None:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError as exc:
        raise RuntimeError("AI Worker 找不到 FFmpeg；無法合成 MP4。") from exc
    if completed.returncode != 0:
        raise RuntimeError(f"{message}：{(completed.stderr or completed.stdout or '')[-500:]}")


def _compose_mp4(root: Path, parts: list[dict], output: Path) -> None:
    segment_paths = []
    for index, part in enumerate(parts, 1):
        segment = root / f"slide-{index}.mp4"
        _run(["ffmpeg", "-y", "-loop", "1", "-i", str(part["image"]), "-i", str(part["audio"]), "-c:v", "libx264", "-tune", "stillimage", "-c:a", "aac", "-b:a", "128k", "-pix_fmt", "yuv420p", "-shortest", "-r", "30", str(segment)], timeout=300, message="FFmpeg 無法合成投影片片段")
        segment_paths.append(segment)
    manifest = root / "concat.txt"; manifest.write_text("".join(f"file '{p.as_posix()}'\n" for p in segment_paths), encoding="utf-8")
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(manifest), "-c", "copy", "-movflags", "+faststart", str(output)], timeout=600, message="FFmpeg 無法合成 MP4")


def generate_video(*, job: Mapping[str, Any], progress_callback: Callable | None = None, storage: VideoStorage | None = None) -> dict:
    existing = repository.get_video_by_source_job(str(job.get("id") or ""))
    if existing: return {"videoId": existing["id"], "replayed": True}
    presentation = presentation_repository.get_presentation(str(job.get("presentationId") or ""))
    if not presentation or str(presentation.get("status") or "") not in {"approved", "published"}:
        raise RuntimeError("AI 影片來源必須是已由授課教師核准的 PowerPoint revision。")
    if presentation.get("group") != job.get("group") or presentation.get("area") != job.get("area"):
        raise RuntimeError("AI 影片工作範圍與 PowerPoint revision 不一致。")
    if not presentation.get("artifactStorageKey") or len(str(presentation.get("artifactSha256") or "")) != 64 or int(presentation.get("artifactBytes") or 0) <= 0:
        raise RuntimeError("PowerPoint revision durable artifact metadata 不完整。")
    slides = [item for item in list(presentation.get("slides") or []) if bool(item.get("enabled", True))]
    if not slides: raise RuntimeError("PowerPoint revision 沒有可用投影片。")
    storage = storage or VideoStorage(); voice = _voice((job.get("request") or {}).get("voice"))
    timeline, captions, parts = [], [], []
    if progress_callback: progress_callback(8, "確認已核准 PowerPoint", "讀取不可變 revision、speaker notes 與安全 provenance")
    with tempfile.TemporaryDirectory(prefix="teacher-video-") as temp:
        root = Path(temp); cursor = 0.0
        for index, slide in enumerate(slides, 1):
            if progress_callback: progress_callback(10 + (45 * index / len(slides)), "產生每頁 AI 語音", f"正在產生第 {index} 頁本機 Kokoro 語音")
            audio_bytes, model = _synthesize(narration_for_slide(slide), voice=voice, instructions="")
            audio = root / f"slide-{index}.wav"; audio.write_bytes(audio_bytes); duration = wav_duration(audio)
            image = root / f"slide-{index}.png"; _write_slide_image(image, slide)
            entry = {"slideNumber": index, "slideId": _safe_text(slide.get("id"), 80), "title": _safe_text(slide.get("title"), 180), "start": round(cursor, 3), "end": round(cursor + duration, 3), "durationSeconds": round(duration, 3)}
            timeline.append(entry); captions.append({"start": cursor, "end": cursor + duration, "text": narration_for_slide(slide)}); parts.append({"audio": audio, "image": image}); cursor += duration
        if progress_callback: progress_callback(62, "建立字幕與時間軸", "輸出 WebVTT / SRT，並保存每頁時間軸")
        vtt, srt = segments_to_vtt(captions), segments_to_srt(captions)
        output = root / "presentation.mp4"
        if progress_callback: progress_callback(72, "FFmpeg 合成 MP4", "依投影片音訊與時間軸合成可預覽影片")
        _compose_mp4(root, parts, output)
        if progress_callback: progress_callback(90, "保存 MP4", "正在將影片直接保存至共享 durable provider")
        artifact = storage.store(output, job_id=str(job.get("id") or ""), filename=f"{_safe_text(presentation.get('title'), 60) or 'AI教學投影片'}-r{presentation.get('revisionNumber') or 1}.mp4")
    video = repository.create_video(presentation=presentation, title=str(presentation.get("title") or "AI 教學影片"), artifact=artifact, duration_seconds=cursor, timeline=timeline, vtt_text=vtt, srt_text=srt, tts={"provider": "kokoro-local", "model": model or DEFAULT_MODEL, "voice": voice}, source_job_id=str(job.get("id") or ""), actor_username=str(job.get("actorUsername") or ""))
    if progress_callback: progress_callback(96, "影片已保存", "等待授課教師預覽與核准")
    return {"videoId": video.get("id", ""), "artifactSha256": video.get("artifactSha256", ""), "artifactBytes": video.get("artifactBytes", 0), "durationSeconds": video.get("durationSeconds", 0), "replayed": False}


__all__ = ["generate_video", "narration_for_slide", "wav_duration"]
