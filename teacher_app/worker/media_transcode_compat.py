"""Media compatibility and accelerated normalization for the material Worker.

Chromium-class browsers may emit microphone-only recordings in a WebM
container.  Stream inspection, safe remux, hardware H.264 selection and CPU
fallback live here so the canonical Worker keeps one media policy.
"""
from __future__ import annotations

from pathlib import Path

from teacher_app.worker import media_acceleration


def _run(worker, command, output: Path, *, timeout: int):
    try:
        completed = worker.subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except worker.subprocess.TimeoutExpired:
        return None, "FFmpeg conversion timed out"
    if completed.returncode == 0 and output.is_file() and output.stat().st_size > 0:
        return completed, ""
    detail = str(completed.stderr or completed.stdout or "").strip()
    return completed, (detail[-300:] or "FFmpeg conversion failed")


def _cpu_video_command(ffmpeg: str, source: Path, output: Path) -> list[str]:
    return [
        ffmpeg,
        "-y",
        "-i",
        str(source),
        "-vf",
        "scale='min(1280,iw)':'min(720,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-movflags",
        "+faststart",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(output),
    ]


def _hardware_video_command(
    ffmpeg: str,
    source: Path,
    output: Path,
    encoder: str,
) -> list[str]:
    return [
        ffmpeg,
        "-y",
        "-i",
        str(source),
        "-vf",
        "scale='min(1280,iw)':'min(720,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2",
        *media_acceleration.encoder_args(encoder),
        "-movflags",
        "+faststart",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(output),
    ]


def transcode_if_needed(worker, source, original, temp):
    """Normalize media using actual streams and fail-safe acceleration.

    Priority:
      1. remux already-web-safe MP4/M4V;
      2. use a hardware H.264 encoder only after a real probe succeeded;
      3. automatically fall back to libx264 if the hardware attempt fails.
    """
    ext = Path(original).suffix.lower()
    if ext not in worker.VIDEO_EXT | worker.AUDIO_EXT:
        return source, original, {}, {}

    ffmpeg = worker._bin("FFMPEG_PATH", "ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg unavailable")

    metadata = worker._probe_media(source)
    has_video = bool(str(metadata.get("videoCodec") or "").strip())
    has_audio = bool(str(metadata.get("audioCodec") or "").strip())

    is_video = ext in worker.VIDEO_EXT and has_video
    is_audio = ext in worker.AUDIO_EXT or (
        ext in worker.VIDEO_EXT and not has_video and has_audio
    )
    if not is_video and not is_audio:
        raise RuntimeError("影音檔未偵測到可用的音訊或視訊串流。")

    timeout = max(
        60,
        min(
            3600,
            int(worker.os.environ.get("MATERIAL_FFMPEG_TIMEOUT_SECONDS", "1800") or 1800),
        ),
    )
    derivatives = {}
    video_codec = str(metadata.get("videoCodec") or "").lower()
    audio_codec = str(metadata.get("audioCodec") or "").lower()
    width = int(metadata.get("width") or 0)
    height = int(metadata.get("height") or 0)

    video_remux = bool(
        is_video
        and ext in {".mp4", ".m4v"}
        and video_codec == "h264"
        and audio_codec in {"", "aac"}
        and 0 < width <= 1280
        and 0 < height <= 720
    )
    audio_remux = bool(is_audio and ext == ".m4a" and audio_codec == "aac")
    hardware_encoder = ""
    hardware_fallback = ""

    if is_video:
        output = Path(temp) / "web.mp4"
        if video_remux:
            command = [
                ffmpeg,
                "-y",
                "-i",
                str(source),
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(output),
            ]
            completed, error = _run(worker, command, output, timeout=timeout)
            if error:
                raise RuntimeError(error)
            transcode_mode = "remux"
        else:
            acceleration = media_acceleration.detect_h264_encoder(worker)
            hardware_encoder = str(acceleration.get("selected") or "")
            completed = None
            error = ""
            if hardware_encoder:
                command = _hardware_video_command(
                    ffmpeg,
                    Path(source),
                    output,
                    hardware_encoder,
                )
                completed, error = _run(worker, command, output, timeout=timeout)
                if error:
                    hardware_fallback = error[:240]
                    output.unlink(missing_ok=True)
            if not hardware_encoder or error:
                command = _cpu_video_command(ffmpeg, Path(source), output)
                completed, cpu_error = _run(worker, command, output, timeout=timeout)
                if cpu_error:
                    raise RuntimeError(f"FFmpeg conversion failed: {cpu_error}")
                transcode_mode = "transcode"
            else:
                transcode_mode = "hardware"
        name = Path(original).with_suffix(".mp4").name
    else:
        output = Path(temp) / "web.m4a"
        command = [
            ffmpeg,
            "-y",
            "-i",
            str(source),
            "-vn",
            "-c:a",
            "copy" if audio_remux else "aac",
        ]
        if not audio_remux:
            command.extend(["-b:a", "128k"])
        command.append(str(output))
        completed, error = _run(worker, command, output, timeout=timeout)
        if error:
            raise RuntimeError(f"FFmpeg conversion failed: {error}")
        name = Path(original).with_suffix(".m4a").name
        transcode_mode = "remux" if audio_remux else "transcode"

    if is_video:
        poster = Path(temp) / "poster.webp"
        audio = Path(temp) / "audio.m4a"
        stamp = max(
            0.0,
            min(30.0, float(metadata.get("durationSeconds") or 0) * 0.1),
        )
        sidecars = (
            (
                [
                    ffmpeg,
                    "-y",
                    "-ss",
                    str(stamp),
                    "-i",
                    str(output),
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale='min(640,iw)':-2",
                    "-c:v",
                    "libwebp",
                    "-quality",
                    "80",
                    str(poster),
                ],
                poster,
            ),
            (
                [
                    ffmpeg,
                    "-y",
                    "-i",
                    str(output),
                    "-vn",
                    "-c:a",
                    "copy",
                    str(audio),
                ],
                audio,
            ),
        )
        for sidecar_cmd, target in sidecars:
            result, sidecar_error = _run(
                worker,
                sidecar_cmd,
                target,
                timeout=min(timeout, 600),
            )
            if result is not None and not sidecar_error:
                derivatives[target.name] = target

    metadata.update(
        {
            "transcoded": True,
            "transcodeMode": transcode_mode,
            "sourceOriginalName": original,
            "mediaKind": "video" if is_video else "audio",
            "normalizedMaxHeight": 720 if is_video else None,
            "videoCrf": 23 if is_video and transcode_mode == "transcode" else None,
            "videoPreset": "veryfast" if is_video and transcode_mode == "transcode" else "",
            "hardwareEncoderUsed": hardware_encoder if transcode_mode == "hardware" else "",
            "hardwareEncoderAttempted": hardware_encoder if hardware_fallback else "",
            "hardwareFallback": hardware_fallback,
        }
    )
    return (
        output,
        name,
        {key: value for key, value in metadata.items() if value not in (None, "")},
        derivatives,
    )


def install(worker) -> None:
    """Install stream-safe media handling and capability reporting."""
    worker._transcode_if_needed = lambda source, original, temp: transcode_if_needed(
        worker, source, original, temp
    )
    if getattr(worker, "_teacher_media_acceleration_installed", False):
        return
    base_capability = worker.capability

    def accelerated_capability():
        values = dict(base_capability() or {})
        try:
            acceleration = media_acceleration.detect_h264_encoder(worker)
            values["videoAcceleration"] = {
                "enabled": bool(acceleration.get("enabled")),
                "available": bool(acceleration.get("available")),
                "encoder": str(acceleration.get("selected") or ""),
                "preference": str(acceleration.get("preference") or "auto"),
            }
        except Exception:
            values["videoAcceleration"] = {
                "enabled": True,
                "available": False,
                "encoder": "",
                "preference": "auto",
            }
        return values

    worker.capability = accelerated_capability
    worker._teacher_media_acceleration_installed = True


__all__ = ["install", "transcode_if_needed"]
