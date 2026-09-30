"""Worker-only approved PowerPoint revision -> renderer chain -> TTS -> captions -> FFmpeg MP4."""
from __future__ import annotations

import subprocess
import tempfile
import time
import wave
from pathlib import Path
from typing import Any, Callable, Mapping

from teacher_app.materials import ai_presentation_quality as presentation_quality
from teacher_app.materials import ai_presentation_repository as presentation_repository
from teacher_app.materials import ai_video_quality as quality
from teacher_app.materials import ai_video_renderer as renderer
from teacher_app.materials import ai_video_repository as repository
from teacher_app.materials.ai_presentation_storage import PPTX_MIME, PresentationStorage
from teacher_app.materials.ai_video_storage import VideoStorage
from teacher_app.materials.media_audio_runtime import DEFAULT_MODEL, _synthesize, _voice
from teacher_app.materials.media_subtitle_runtime import segments_to_srt, segments_to_vtt


def _safe_text(value: Any, limit=4000) -> str:
    text = " ".join(str(value or "").replace("\x00", " ").split())[:limit]
    lowered = text.lower()
    if any(marker in lowered for marker in ("token=", "password=", "secret=", "api_key=", "authorization:", "bearer ")) or "/home/" in lowered or "\\users\\" in lowered:
        raise ValueError("影片 provenance 或講稿含有不允許的敏感資訊或本機路徑。")
    return text


def _block_narration(block: Mapping[str, Any]) -> list[str]:
    kind = str(block.get("type") or "").lower()
    if kind == "table":
        output = [_safe_text(value, 120) for value in list(block.get("headers") or [])]
        for row in list(block.get("rows") or [])[:7]:
            if isinstance(row, list):
                output.append("，".join(_safe_text(value, 160) for value in row))
        return [item for item in output if item]
    if kind == "comparison":
        values = [_safe_text(block.get("leftTitle"), 120)]
        values.extend(_safe_text(value, 180) for value in list(block.get("leftItems") or [])[:5])
        values.append(_safe_text(block.get("rightTitle"), 120))
        values.extend(_safe_text(value, 180) for value in list(block.get("rightItems") or [])[:5])
        return [item for item in values if item]
    if kind == "chart":
        labels = [_safe_text(value, 80) for value in list(block.get("labels") or [])[:12]]
        values = [_safe_text(value, 80) for value in list(block.get("values") or [])[:12]]
        return ["，".join(f"{label} {value}" for label, value in zip(labels, values))]
    if kind == "image":
        return [item for item in (_safe_text(block.get("caption"), 240), _safe_text(block.get("sourceLabel"), 160)) if item]
    if kind == "callout":
        return [_safe_text(block.get("text") or block.get("caption"), 600)]
    return []


def narration_for_slide(slide: Mapping[str, Any]) -> str:
    notes = _safe_text(slide.get("speakerNotes"), 4000)
    if notes:
        return notes
    values = [_safe_text(slide.get("title"), 300)]
    values.extend(_safe_text(item, 700) for item in list(slide.get("bullets") or [])[:8])
    for block in list(slide.get("blocks") or [])[:8]:
        if isinstance(block, Mapping):
            values.extend(_block_narration(block))
    return "。".join(part for part in values if part)[:4000] or "本頁投影片內容。"


def _prepared_slides(presentation: Mapping[str, Any]) -> list[dict[str, Any]]:
    prepared, _manifest = presentation_quality.prepare_slides(
        list(presentation.get("slides") or []), provenance_present=True,
    )
    original_ids = {
        str(item.get("id") or "")
        for item in list(presentation.get("slides") or [])
        if isinstance(item, Mapping)
    }
    for item in prepared:
        if str(item.get("id") or "") not in original_ids:
            item["speakerNotes"] = ""
    if not prepared or str(prepared[0].get("layout") or "").lower() != "title":
        prepared.insert(
            0,
            {
                "id": "phase4-cover",
                "order": 1,
                "enabled": True,
                "title": _safe_text(presentation.get("title"), 180) or "AI 教學投影片",
                "bullets": [],
                "layout": "title",
                "blocks": [],
                "speakerNotes": "",
            },
        )
    for index, item in enumerate(prepared, 1):
        item["order"] = index
    return prepared


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as source:
        frames, rate = source.getnframes(), source.getframerate()
    return max(0.2, float(frames) / max(1, rate))


def _write_slide_image(path: Path, slide: Mapping[str, Any]) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise RuntimeError("AI Worker 缺少 Pillow，無法建立影片投影片安全備援影格。") from exc
    image = Image.new("RGB", (1280, 720), "#0f172a")
    draw = ImageDraw.Draw(image)
    font_path = "C:/Windows/Fonts/msjh.ttc" if Path("C:/Windows/Fonts/msjh.ttc").is_file() else None
    try:
        title_font = ImageFont.truetype(font_path, 46) if font_path else ImageFont.load_default()
        body_font = ImageFont.truetype(font_path, 28) if font_path else ImageFont.load_default()
    except Exception:
        title_font = body_font = ImageFont.load_default()
    draw.text((70, 70), _safe_text(slide.get("title"), 180), fill="white", font=title_font)
    y = 180
    text_items = list(slide.get("bullets") or [])[:8]
    if not text_items:
        text_items = [narration_for_slide(slide)]
    for bullet in text_items:
        text = _safe_text(bullet, 500)
        while text and y < 650:
            line, text = text[:42], text[42:]
            draw.text((100, y), "• " + line, fill="#dbeafe", font=body_font)
            y += 44
    image.save(path, "PNG")


def _run(command: list[str], *, timeout: int, message: str) -> None:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError as exc:
        raise RuntimeError(message) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{message}（逾時）") from exc
    if completed.returncode != 0:
        raise RuntimeError(f"{message}（exit={completed.returncode}）")


def _export_powerpoint_frames(pptx_path: Path, output_dir: Path) -> list[Path]:
    """Backward-compatible test seam; Phase 6 orchestration lives in ai_video_renderer."""
    frames, _detail = renderer.export_powerpoint_frames(pptx_path, output_dir)
    return frames


def _export_libreoffice_frames(pptx_path: Path, output_dir: Path) -> list[Path]:
    frames, _detail = renderer.export_libreoffice_frames(pptx_path, output_dir)
    return frames


def _presentation_location(presentation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "backend": presentation.get("artifactBackend"),
        "key": presentation.get("artifactStorageKey"),
        "sha256": presentation.get("artifactSha256"),
    }


def _render_frames(
    presentation: Mapping[str, Any],
    slides: list[dict[str, Any]],
    root: Path,
    presentation_storage: PresentationStorage | None = None,
) -> tuple[list[Path], str, list[dict[str, str]]]:
    # Retrieval/checksum failure is not a rendering fallback condition. We must
    # have the exact immutable PPTX before selecting any frame renderer.
    source = (presentation_storage or PresentationStorage()).download(
        _presentation_location(presentation), root / "approved-source.pptx",
    )
    frames, selected, attempts = renderer.render_exact_frames(
        source,
        expected_count=len(slides),
        root=root,
    )
    if frames and selected:
        return frames, selected, attempts

    fallback_dir = root / "fallback-frames"
    fallback_dir.mkdir(parents=True, exist_ok=True)
    fallback_frames: list[Path] = []
    for index, slide in enumerate(slides, 1):
        path = fallback_dir / f"slide-{index:04d}.png"
        _write_slide_image(path, slide)
        fallback_frames.append(path)
    attempts.append(
        {
            "renderer": renderer.SAFE_FALLBACK,
            "status": "success",
            "detail": "safe-text-renderer",
        }
    )
    return fallback_frames, renderer.SAFE_FALLBACK, attempts


def _compose_mp4(root: Path, parts: list[dict], output: Path) -> None:
    segment_paths = []
    for index, part in enumerate(parts, 1):
        segment = root / f"segment-{index:04d}.mp4"
        _run(
            [
                "ffmpeg",
                "-y",
                "-loop",
                "1",
                "-i",
                str(part["image"]),
                "-i",
                str(part["audio"]),
                "-c:v",
                "libx264",
                "-tune",
                "stillimage",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-pix_fmt",
                "yuv420p",
                "-shortest",
                "-r",
                "30",
                str(segment),
            ],
            timeout=300,
            message="FFmpeg 無法合成投影片片段",
        )
        segment_paths.append(segment)
    manifest = root / "concat.txt"
    manifest.write_text("".join(f"file '{path.as_posix()}'\n" for path in segment_paths), encoding="utf-8")
    _run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(manifest), "-c", "copy", "-movflags", "+faststart", str(output)],
        timeout=600,
        message="FFmpeg 無法合成 MP4",
    )


def generate_video(
    *,
    job: Mapping[str, Any],
    progress_callback: Callable | None = None,
    storage: VideoStorage | None = None,
    presentation_storage: PresentationStorage | None = None,
) -> dict:
    existing = repository.get_video_by_source_job(str(job.get("id") or ""))
    if existing:
        return {"videoId": existing["id"], "replayed": True}
    presentation = presentation_repository.get_presentation(str(job.get("presentationId") or ""))
    if not presentation or str(presentation.get("status") or "") not in {"approved", "published"}:
        raise RuntimeError("AI 影片來源必須是已由授課教師核准的 PowerPoint revision。")
    if presentation.get("group") != job.get("group") or presentation.get("area") != job.get("area"):
        raise RuntimeError("AI 影片工作範圍與 PowerPoint revision 不一致。")
    if (
        str(presentation.get("artifactMimeType") or PPTX_MIME) != PPTX_MIME
        or not presentation.get("artifactStorageKey")
        or len(str(presentation.get("artifactSha256") or "")) != 64
        or int(presentation.get("artifactBytes") or 0) <= 0
    ):
        raise RuntimeError("PowerPoint revision durable artifact metadata 不完整。")
    slides = _prepared_slides(presentation)
    if not slides:
        raise RuntimeError("PowerPoint revision 沒有可用投影片。")
    storage = storage or VideoStorage()
    voice = _voice((job.get("request") or {}).get("voice"))
    timeline, captions, parts = [], [], []
    started = time.perf_counter()
    model = DEFAULT_MODEL
    if progress_callback:
        progress_callback(8, "確認已核准 PowerPoint", "讀取不可變 revision、正式 PPTX artifact 與安全 provenance")
    with tempfile.TemporaryDirectory(prefix="teacher-video-") as temp:
        root = Path(temp)
        if progress_callback:
            progress_callback(
                14,
                "選擇投影片 renderer",
                "依序嘗試 PowerPoint COM、LibreOffice headless；都不可用才使用安全文字備援",
            )
        frames, frame_renderer, renderer_attempts = _render_frames(
            presentation,
            slides,
            root,
            presentation_storage=presentation_storage,
        )
        cursor = 0.0
        for index, (slide, image) in enumerate(zip(slides, frames), 1):
            if progress_callback:
                progress_callback(
                    18 + (42 * index / len(slides)),
                    "產生每頁 AI 語音",
                    f"正在產生第 {index} 頁本機 Kokoro 語音",
                )
            narration = narration_for_slide(slide)
            audio_bytes, model = _synthesize(narration, voice=voice, instructions="")
            audio = root / f"slide-{index:04d}.wav"
            audio.write_bytes(audio_bytes)
            duration = wav_duration(audio)
            entry = {
                "slideNumber": index,
                "slideId": _safe_text(slide.get("id"), 80),
                "title": _safe_text(slide.get("title"), 180),
                "start": round(cursor, 3),
                "end": round(cursor + duration, 3),
                "durationSeconds": round(duration, 3),
            }
            timeline.append(entry)
            captions.append({"start": cursor, "end": cursor + duration, "text": narration})
            parts.append({"audio": audio, "image": image})
            cursor += duration
        if progress_callback:
            progress_callback(64, "建立字幕與時間軸", "輸出 WebVTT / SRT，並驗證每頁時間軸與 Phase 4 拆頁結果")
        vtt, srt = segments_to_vtt(captions), segments_to_srt(captions)
        quality_manifest = quality.evaluate_render(
            prepared_slides=slides,
            timeline=timeline,
            vtt_text=vtt,
            srt_text=srt,
            frame_renderer=frame_renderer,
            presentation_sha256=str(presentation.get("artifactSha256") or ""),
        )
        if quality_manifest.get("status") == "error":
            raise RuntimeError("AI 影片品質檢查發現阻擋錯誤，已停止產生。")
        output = root / "presentation.mp4"
        if progress_callback:
            progress_callback(74, "FFmpeg 合成 MP4", "依正式投影片畫面、Kokoro 語音與時間軸合成影片")
        _compose_mp4(root, parts, output)
        if progress_callback:
            progress_callback(90, "保存 MP4", "正在將影片直接保存至共享 durable provider")
        artifact = storage.store(
            output,
            job_id=str(job.get("id") or ""),
            filename=f"{_safe_text(presentation.get('title'), 60) or 'AI教學投影片'}-r{presentation.get('revisionNumber') or 1}.mp4",
        )
    metrics = quality.sanitize_render_metrics(
        {
            "rulesetVersion": quality.RULESET_VERSION,
            "durationMs": round((time.perf_counter() - started) * 1000),
            "attempts": int(job.get("attempts") or 0),
            "renderedSlideCount": len(slides),
            "ttsSegmentCount": len(parts),
            "ffmpegSegmentCount": len(parts),
            "frameRenderer": frame_renderer,
            "rendererAttempts": renderer_attempts,
            "jobId": str(job.get("id") or ""),
        }
    )
    video = repository.create_video(
        presentation=presentation,
        title=str(presentation.get("title") or "AI 教學影片"),
        artifact=artifact,
        duration_seconds=cursor,
        timeline=timeline,
        vtt_text=vtt,
        srt_text=srt,
        tts={"provider": "kokoro-local", "model": model or DEFAULT_MODEL, "voice": voice},
        source_job_id=str(job.get("id") or ""),
        actor_username=str(job.get("actorUsername") or ""),
        quality_manifest=quality_manifest,
        render_metrics=metrics,
        frame_renderer=frame_renderer,
        render_ruleset_version=quality.RULESET_VERSION,
    )
    if progress_callback:
        progress_callback(96, "影片已保存", "品質檢查完成；等待授課教師預覽與核准")
    return {
        "videoId": video.get("id", ""),
        "artifactSha256": video.get("artifactSha256", ""),
        "artifactBytes": video.get("artifactBytes", 0),
        "durationSeconds": video.get("durationSeconds", 0),
        "qualityStatus": (video.get("qualityManifest") or {}).get("status", ""),
        "frameRenderer": video.get("frameRenderer", ""),
        "rendererAttempts": metrics.get("rendererAttempts", []),
        "replayed": False,
    }


__all__ = [
    "generate_video",
    "narration_for_slide",
    "wav_duration",
    "_prepared_slides",
    "_export_powerpoint_frames",
    "_export_libreoffice_frames",
]
