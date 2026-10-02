"""10/14 media compatibility layer for browser-recorded WebM.

Chromium-class browsers may emit microphone-only recordings in a WebM
container. The adapter also owns the fast media normalization path used by the
Windows material Worker.
"""
from __future__ import annotations

from pathlib import Path


def transcode_if_needed(worker, source, original, temp):
    """Normalize media from ffprobe streams and remux web-safe media."""
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
        else:
            command = [
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
        name = Path(original).with_suffix(".m4a").name

    try:
        completed = worker.subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except worker.subprocess.TimeoutExpired:
        raise RuntimeError("FFmpeg conversion timed out")
    if completed.returncode != 0 or not output.is_file() or output.stat().st_size <= 0:
        raise RuntimeError(
            f"FFmpeg conversion failed: {(completed.stderr or '')[-300:]}"
        )

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
            try:
                result = worker.subprocess.run(
                    sidecar_cmd,
                    capture_output=True,
                    text=True,
                    timeout=min(timeout, 600),
                    check=False,
                )
            except worker.subprocess.TimeoutExpired:
                result = None
            if (
                result is not None
                and result.returncode == 0
                and target.is_file()
                and target.stat().st_size > 0
            ):
                derivatives[target.name] = target

    fast_path = video_remux or audio_remux
    metadata.update(
        {
            "transcoded": True,
            "transcodeMode": "remux" if fast_path else "transcode",
            "sourceOriginalName": original,
            "mediaKind": "video" if is_video else "audio",
            "normalizedMaxHeight": 720 if is_video else None,
            "videoCrf": 23 if is_video and not video_remux else None,
            "videoPreset": "veryfast" if is_video and not video_remux else "",
        }
    )
    return (
        output,
        name,
        {key: value for key, value in metadata.items() if value is not None},
        derivatives,
    )


def install(worker) -> None:
    """Install the narrow compatibility override on the imported Worker module."""
    worker._transcode_if_needed = lambda source, original, temp: transcode_if_needed(
        worker, source, original, temp
    )


__all__ = ["install", "transcode_if_needed"]
