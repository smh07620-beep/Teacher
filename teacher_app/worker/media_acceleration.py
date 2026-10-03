"""Hardware video acceleration selection for the standalone material Worker.

The Worker never trusts FFmpeg's compiled-in encoder list alone.  Hardware
encoders are accepted only after a tiny real encode probe succeeds on the
current host.  Results are cached for the process lifetime.
"""
from __future__ import annotations

import os
import threading


_LOCK = threading.Lock()
_CACHE: dict[tuple[str, str, bool], dict[str, object]] = {}
_ENCODERS = {
    "qsv": "h264_qsv",
    "nvenc": "h264_nvenc",
    "amf": "h264_amf",
}
_AUTO_ORDER = ("qsv", "nvenc", "amf")


def _env_true(env, name: str, default: bool) -> bool:
    fallback = "true" if default else "false"
    return str(env.get(name, fallback) or fallback).strip().lower() not in {
        "0", "false", "no", "off"
    }


def _preference(env) -> str:
    value = str(env.get("MATERIAL_VIDEO_HARDWARE_ENCODER", "auto") or "auto").strip().lower()
    return value if value in {"auto", "qsv", "nvenc", "amf", "cpu"} else "auto"


def _probe(worker, ffmpeg: str, encoder: str) -> tuple[bool, str]:
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=size=64x64:rate=1",
        "-frames:v",
        "1",
        "-an",
        "-c:v",
        encoder,
        "-f",
        "null",
        "-",
    ]
    try:
        completed = worker.subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (worker.subprocess.TimeoutExpired, OSError) as exc:
        return False, type(exc).__name__
    if completed.returncode == 0:
        return True, ""
    detail = str(completed.stderr or completed.stdout or "").strip().replace("\r", " ").replace("\n", " ")
    return False, detail[-240:]


def detect_h264_encoder(worker, *, refresh: bool = False) -> dict[str, object]:
    """Return the first hardware H.264 encoder proven usable on this host."""
    env = worker.os.environ
    enabled = _env_true(env, "MATERIAL_VIDEO_HARDWARE_ACCELERATION", True)
    preference = _preference(env)
    ffmpeg = worker._bin("FFMPEG_PATH", "ffmpeg")
    key = (str(ffmpeg or ""), preference, enabled)
    with _LOCK:
        if not refresh and key in _CACHE:
            return dict(_CACHE[key])

    result: dict[str, object] = {
        "enabled": enabled,
        "preference": preference,
        "selected": "",
        "available": False,
        "tested": [],
    }
    if not enabled or preference == "cpu" or not ffmpeg:
        with _LOCK:
            _CACHE[key] = dict(result)
        return result

    order = _AUTO_ORDER if preference == "auto" else (preference,)
    tested = []
    for kind in order:
        encoder = _ENCODERS[kind]
        ok, error = _probe(worker, ffmpeg, encoder)
        tested.append({"kind": kind, "encoder": encoder, "ok": ok, "error": error})
        if ok:
            result.update({"selected": encoder, "selectedKind": kind, "available": True})
            break
    result["tested"] = tested
    with _LOCK:
        _CACHE[key] = dict(result)
    return dict(result)


def encoder_args(encoder: str) -> list[str]:
    """Return conservative cross-hardware H.264 options.

    The quality target intentionally uses bitrate controls accepted by QSV,
    NVENC and AMF.  If a driver rejects these at runtime, the caller falls back
    to libx264 for the same job.
    """
    if encoder not in set(_ENCODERS.values()):
        return []
    return [
        "-c:v",
        encoder,
        "-b:v",
        "2500k",
        "-maxrate",
        "3500k",
        "-bufsize",
        "5000k",
    ]


def reset_cache() -> None:
    with _LOCK:
        _CACHE.clear()


__all__ = ["detect_h264_encoder", "encoder_args", "reset_cache"]
