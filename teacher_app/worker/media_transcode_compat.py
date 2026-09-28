"""10/14 media compatibility layer for browser-recorded WebM.

Chromium-class browsers may emit microphone-only recordings in a WebM
container.  The legacy local Worker historically classified ``.webm`` as
video from the filename alone.  This adapter keeps the mature Worker runtime
unchanged while making the media decision from ffprobe stream metadata.
"""
from __future__ import annotations

from pathlib import Path


def transcode_if_needed(worker, source, original, temp):
    """Normalize media using actual streams instead of the file suffix alone."""
    ext = Path(original).suffix.lower()
    if ext not in worker.VIDEO_EXT | worker.AUDIO_EXT:
        return source, original, {}, {}

    ffmpeg = worker._bin("FFMPEG_PATH", "ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg unavailable")

    metadata = worker._probe_media(source)
    has_video = bool(str(metadata.get("videoCodec") or "").strip())
    has_audio = bool(str(metadata.get("audioCodec") or "").strip())

    # An explicitly audio extension stays audio.  Ambiguous containers such as
    # .webm/.mp4 use ffprobe: a video stream means video; audio-only means audio.
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

    if is_video:
        output = Path(temp) / "web.mp4"
        command = [
            ffmpeg, "-y", "-i", str(source),
            "-vf", "scale='min(1280,iw)':'min(720,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-movflags", "+faststart", "-c:a", "aac", "-b:a", "128k", str(output),
        ]
        name = Path(original).with_suffix(".mp4").name
    else:
        output = Path(temp) / "web.m4a"
        command = [
            ffmpeg, "-y", "-i", str(source),
            "-vn", "-c:a", "aac", "-b:a", "128k", str(output),
        ]
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
                    ffmpeg, "-y", "-ss", str(stamp), "-i", str(output),
                    "-frames:v", "1", "-vf", "scale='min(640,iw)':-2",
                    "-c:v", "libwebp", "-quality", "80", str(poster),
                ],
                poster,
            ),
            (
                [
                    ffmpeg, "-y", "-i", str(output), "-vn", "-c:a", "aac",
                    "-b:a", "64k", str(audio),
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

    metadata.update(
        {
            "transcoded": True,
            "sourceOriginalName": original,
            "mediaKind": "video" if is_video else "audio",
            "normalizedMaxHeight": 720 if is_video else None,
            "videoCrf": 23 if is_video else None,
            "videoPreset": "veryfast" if is_video else "",
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
