"""Worker-only approved PowerPoint revision -> renderer chain -> TTS -> captions -> FFmpeg MP4."""
from __future__ import annotations

import subprocess
import tempfile
import time
import wave
import hashlib
import json
import os
import shutil
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


VIDEO_ENCODING = {
    "fps": 5,
    "codec": "libx264",
    "preset": "veryfast",
    "tune": "stillimage",
    "crf": 23,
    "pix_fmt": "yuv420p",
    "audio_codec": "aac",
    "audio_bitrate": "128k",
    "audio_rate": 24000,
    "threads": 2,
    "size": "1280:720",
}
_QSV_AVAILABLE: bool | None = None


def _cache_root() -> Path:
    default = r"C:\TeacherWorker\.video_cache" if os.name == "nt" else "/var/tmp/teacher-video-cache"
    return Path(str(os.environ.get("AI_VIDEO_CACHE_DIR") or default)).expanduser()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _ffmpeg() -> str:
    configured = str(os.environ.get("FFMPEG_PATH") or "").strip()
    if configured and Path(configured).is_file():
        return configured
    return shutil.which("ffmpeg") or "ffmpeg"


def _qsv_available() -> bool:
    global _QSV_AVAILABLE
    requested = str(os.environ.get("AI_VIDEO_QSV_ENABLED", "false") or "false").strip().lower()
    if requested not in {"1", "true", "yes", "on"}:
        return False
    if _QSV_AVAILABLE is not None:
        return _QSV_AVAILABLE
    try:
        completed = subprocess.run([_ffmpeg(), "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=15, check=False)
        _QSV_AVAILABLE = completed.returncode == 0 and "h264_qsv" in (completed.stdout + completed.stderr)
    except (OSError, subprocess.TimeoutExpired):
        _QSV_AVAILABLE = False
    return _QSV_AVAILABLE


def _segment_key(image: Path, audio: Path, *, encoder: str) -> str:
    payload = {"image": _hash_file(image), "audio": _hash_file(audio), "encoder": encoder, "encoding": VIDEO_ENCODING}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _segment_command(image: Path, audio: Path, target: Path, *, encoder: str = "libx264") -> list[str]:
    command = [
        _ffmpeg(), "-y", "-loop", "1", "-framerate", str(VIDEO_ENCODING["fps"]), "-i", str(image), "-i", str(audio),
        "-threads", str(VIDEO_ENCODING["threads"]), "-c:v", encoder,
    ]
    if encoder == "libx264":
        command += ["-preset", VIDEO_ENCODING["preset"], "-tune", VIDEO_ENCODING["tune"], "-crf", str(VIDEO_ENCODING["crf"])]
    else:
        command += ["-global_quality", str(VIDEO_ENCODING["crf"])]
    return command + [
        "-vf", f"scale={VIDEO_ENCODING['size']}:force_original_aspect_ratio=decrease,pad={VIDEO_ENCODING['size']}:(ow-iw)/2:(oh-ih)/2",
        "-c:a", VIDEO_ENCODING["audio_codec"], "-b:a", VIDEO_ENCODING["audio_bitrate"], "-ar", str(VIDEO_ENCODING["audio_rate"]),
        "-pix_fmt", VIDEO_ENCODING["pix_fmt"], "-shortest", "-movflags", "+faststart", str(target),
    ]


def _concat_command(manifest: Path, output: Path) -> list[str]:
    return [_ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(manifest), "-c", "copy", "-movflags", "+faststart", str(output)]


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
    # A LibreOffice/COM export always renders a complete deck. Cache those
    # rasterized pages by immutable deck content so an unchanged revision does
    # not launch Office again on later video jobs.
    deck_hash = _hash_file(source)
    cache_dir = _cache_root() / "frames" / deck_hash
    manifest_path = cache_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        cached = [cache_dir / name for name in list(manifest.get("files") or [])]
        if len(cached) == len(slides) and all(item.is_file() and item.stat().st_size > 0 for item in cached):
            restored = []
            restored_dir = root / "cached-frames"
            restored_dir.mkdir(parents=True, exist_ok=True)
            for index, item in enumerate(cached, 1):
                destination = restored_dir / f"slide-{index:04d}.png"
                shutil.copyfile(item, destination)
                restored.append(destination)
            return restored, str(manifest.get("renderer") or renderer.SAFE_FALLBACK), list(manifest.get("attempts") or [])
    except (OSError, ValueError, TypeError):
        pass
    frames, selected, attempts = renderer.render_exact_frames(
        source,
        expected_count=len(slides),
        root=root,
    )
    if frames and selected:
        _store_frame_cache(cache_dir, frames, selected, attempts)
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
    _store_frame_cache(cache_dir, fallback_frames, renderer.SAFE_FALLBACK, attempts)
    return fallback_frames, renderer.SAFE_FALLBACK, attempts


def _store_frame_cache(cache_dir: Path, frames: list[Path], selected: str, attempts: list[dict[str, str]]) -> None:
    try:
        staging = cache_dir.with_name(cache_dir.name + f".tmp-{os.getpid()}")
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True, exist_ok=True)
        names = []
        for index, frame in enumerate(frames, 1):
            name = f"slide-{index:04d}.png"
            shutil.copyfile(frame, staging / name)
            names.append(name)
        (staging / "manifest.json").write_text(json.dumps({"renderer": selected, "attempts": attempts, "files": names}, ensure_ascii=False), encoding="utf-8")
        cache_dir.parent.mkdir(parents=True, exist_ok=True)
        if cache_dir.exists():
            shutil.rmtree(staging, ignore_errors=True)
        else:
            os.replace(staging, cache_dir)
    except OSError:
        pass


def _compose_mp4(root: Path, parts: list[dict], output: Path, *, progress_callback: Callable | None = None) -> dict[str, int | str]:
    segment_paths = []
    hits = 0
    started = time.perf_counter()
    requested_encoder = "h264_qsv" if _qsv_available() else "libx264"
    for index, part in enumerate(parts, 1):
        segment = root / f"segment-{index:04d}.mp4"
        key = _segment_key(part["image"], part["audio"], encoder=requested_encoder)
        cached = _cache_root() / "segments" / f"{key}.mp4"
        if cached.is_file() and cached.stat().st_size > 1024:
            shutil.copyfile(cached, segment)
            hits += 1
        else:
            temporary = cached.with_name(f"{cached.name}.{os.getpid()}.tmp")
            try:
                cached.parent.mkdir(parents=True, exist_ok=True)
                _run(_segment_command(part["image"], part["audio"], temporary, encoder=requested_encoder), timeout=300, message="FFmpeg 無法合成投影片片段")
            except RuntimeError:
                if requested_encoder != "h264_qsv":
                    raise
                # Encoder availability is not enough: an Intel driver may be
                # absent or busy. Retry this page with the default CPU codec.
                _run(_segment_command(part["image"], part["audio"], temporary, encoder="libx264"), timeout=300, message="FFmpeg 無法以 x264 合成投影片片段")
                requested_encoder = "libx264"
                key = _segment_key(part["image"], part["audio"], encoder=requested_encoder)
                cached = _cache_root() / "segments" / f"{key}.mp4"
            try:
                os.replace(temporary, cached)
            except OSError:
                shutil.copyfile(temporary, segment)
            else:
                shutil.copyfile(cached, segment)
        if progress_callback:
            progress_callback(74 + (14 * index / max(1, len(parts))), "編碼投影片片段", f"第 {index}/{len(parts)} 頁；segment cache {'命中' if segment.exists() and cached.exists() else '重建'}")
        segment_paths.append(segment)
    manifest = root / "concat.txt"
    manifest.write_text("".join(f"file '{path.as_posix()}'\n" for path in segment_paths), encoding="utf-8")
    if progress_callback:
        progress_callback(89, "無重編碼合併 MP4", "以 concat demuxer 直接複製每頁片段並加入 faststart")
    segment_ms = round((time.perf_counter() - started) * 1000)
    concat_started = time.perf_counter()
    _run(_concat_command(manifest, output), timeout=600, message="FFmpeg 無法合成 MP4")
    return {"segmentCacheHits": hits, "encoder": requested_encoder, "segmentEncodeMs": segment_ms, "concatMs": round((time.perf_counter() - concat_started) * 1000)}


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
    stage_started = started
    stage_timings: dict[str, int] = {}
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
        stage_timings["slideRenderMs"] = round((time.perf_counter() - stage_started) * 1000)
        stage_started = time.perf_counter()
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
        stage_timings["ttsMs"] = round((time.perf_counter() - stage_started) * 1000)
        stage_started = time.perf_counter()
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
            progress_callback(74, "FFmpeg 編碼", "使用 5fps 靜態投影片參數，逐頁重用可用 segment cache")
        compose_metrics = _compose_mp4(root, parts, output, progress_callback=progress_callback)
        stage_timings["segmentEncodeMs"] = int(compose_metrics.get("segmentEncodeMs", 0) or 0)
        stage_timings["concatMs"] = int(compose_metrics.get("concatMs", 0) or 0)
        stage_started = time.perf_counter()
        if progress_callback:
            progress_callback(90, "保存 MP4", "正在將影片直接保存至共享 durable provider")
        artifact = storage.store(
            output,
            job_id=str(job.get("id") or ""),
            filename=f"{_safe_text(presentation.get('title'), 60) or 'AI教學投影片'}-r{presentation.get('revisionNumber') or 1}.mp4",
        )
        stage_timings["publishMs"] = round((time.perf_counter() - stage_started) * 1000)
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
            "stageTimingsMs": stage_timings,
            "segmentCacheHits": compose_metrics.get("segmentCacheHits", 0),
            "encoder": compose_metrics.get("encoder", "libx264"),
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
