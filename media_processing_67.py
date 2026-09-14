"""Media capability helpers for the single durable material worker.

Scheme B intentionally has no second media queue or placeholder worker. Video
and audio uploads are material_jobs consumed by material_worker.py.
"""
from __future__ import annotations

import shutil
import subprocess


def _binary_capability(binary: str, args: list[str], label: str):
    path = shutil.which(binary) if binary == "ffmpeg" else binary
    if not path:
        return {"available": False, "binary": "", "reason": f"{label} not installed"}
    try:
        completed = subprocess.run([path, *args], capture_output=True, text=True, timeout=5, check=False)
        return {"available": completed.returncode == 0, "binary": path, "reason": "" if completed.returncode == 0 else f"{label} failed capability check"}
    except subprocess.TimeoutExpired:
        return {"available": False, "binary": path, "reason": f"{label} capability check timed out"}
    except OSError as exc:
        return {"available": False, "binary": path, "reason": str(exc)[:160]}


def ffmpeg_capability():
    return _binary_capability("ffmpeg", ["-version"], "ffmpeg")


def libreoffice_capability(binary: str = "soffice"):
    return _binary_capability(binary, ["--version"], "LibreOffice")


def worker_architecture(staging: dict | None = None):
    """Safe metadata for an admin capability endpoint, never an online claim."""
    return {
        "queueBackend": "material_jobs",
        "sharedStaging": (staging or {}).get("backend", ""),
        "workerArchitecture": "render-background-worker",
        "workerRequired": True,
    }
