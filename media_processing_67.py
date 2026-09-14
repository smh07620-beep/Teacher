"""Durable, opt-in media processing primitives; never run work in HTTP threads."""
from __future__ import annotations
import shutil, subprocess
from pathlib import Path

def ffmpeg_capability():
    binary=shutil.which("ffmpeg")
    if not binary:return {"available":False,"binary":"","reason":"ffmpeg not installed"}
    try:
        out=subprocess.run([binary,"-version"],capture_output=True,text=True,timeout=5,check=False)
        return {"available":out.returncode==0,"binary":binary,"reason":"" if out.returncode==0 else "ffmpeg failed capability check"}
    except subprocess.TimeoutExpired:return {"available":False,"binary":binary,"reason":"ffmpeg capability check timed out"}

def worker_once(base):
    """Reserved worker entrypoint. Deployment must run this separately from web."""
    return {"processed":0,"capability":ffmpeg_capability()}
