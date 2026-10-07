#!/usr/bin/env python3
"""Weekly check: every voice the product offers exists in the Hugging Face repo.

The voice list is hard-coded in ``media_audio_runtime.ALLOWED_VOICES``.  If the
upstream repo renames/removes a voice file, a teacher picks it, the Worker fails
to download it and the job dies.  This reads the public model listing (no token)
and fails when any allowed voice's ``voices/<id>.pt`` file is missing.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from teacher_app.materials import media_audio_runtime as runtime  # noqa: E402


def fetch_siblings(repo_id: str) -> list[str]:
    request = urllib.request.Request(
        f"https://huggingface.co/api/models/{repo_id}", headers={"User-Agent": "TeacherVoiceCheck/1.0"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - fixed https host
        payload = json.loads(response.read().decode("utf-8"))
    return [str(item.get("rfilename") or "") for item in payload.get("siblings") or []]


def missing_voices(files: list[str], voices: set[str] | None = None) -> list[str]:
    present = set(files)
    return sorted(v for v in (voices if voices is not None else runtime.ALLOWED_VOICES) if f"voices/{v}.pt" not in present)


def check(repo_id: str = runtime.DEFAULT_REPO_ID, fetcher: Callable[[str], list[str]] = fetch_siblings) -> dict:
    files = fetcher(repo_id)
    if not files:
        raise RuntimeError(f"Hugging Face 回傳空的檔案清單：{repo_id}")
    missing = missing_voices(files)
    return {"repo": repo_id, "ok": not missing, "missing": missing, "checked": sorted(runtime.ALLOWED_VOICES)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=runtime.DEFAULT_REPO_ID)
    args = parser.parse_args(argv)
    try:
        result = check(args.repo)
    except Exception as exc:  # noqa: BLE001
        print(f"::error::無法查詢 Hugging Face：{type(exc).__name__}: {str(exc)[:200]}")
        return 1
    Path("kokoro-voices-report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if result["missing"]:
        print(f"::error::Hugging Face 上缺少語音檔：{', '.join(result['missing'])}（請更新 ALLOWED_VOICES 與前端選單）")
        return 1
    print(f"[voices] {len(result['checked'])} voices all present in {args.repo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
