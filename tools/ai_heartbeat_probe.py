#!/usr/bin/env python3
"""Send ONE real AI Worker heartbeat from this computer and print the site's answer.

Run from the Worker checkout (inside its .venv)::

    .\\.venv\\Scripts\\python.exe tools\\ai_heartbeat_probe.py

It uses the same client, worker id and capabilities as the real AI Worker, so a
success here means the website has recorded an AI Worker heartbeat.  Nothing
secret is printed.  The real Worker overwrites this heartbeat within ~30 seconds.
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _preload_env_file() -> None:
    # Must run before importing teacher_app: storage/providers reads env at import.
    path = ROOT / ".local-worker.env"
    if not path.is_file():
        return
    line = re.compile(r"^\s*([^#=\s]+)\s*=\s*(.*?)\s*$")
    for text in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        match = line.match(text)
        if match:
            os.environ[match.group(1)] = match.group(2)


def main() -> int:
    _preload_env_file()
    base = str(os.environ.get("TEACHER_BASE_URL") or "").strip().rstrip("/")
    print(f"網站網址: {base or '(未設定)'}")
    try:
        import ai_question_worker as worker
        from teacher_app.worker import ai_remote

        worker_id = worker._ai_worker_id()
        print(f"AI Worker 編號: {worker_id}")
        print(f"回報傳輸方式: {ai_remote.transport_mode()}")
        api = ai_remote.AIWorkerApi(worker_id=worker_id)
        answer = api.heartbeat(worker._ai_worker_capabilities(ai_remote.TRANSPORT_HTTPS))
    except Exception as exc:  # never print a traceback that could echo settings
        print(f"[失敗] {type(exc).__name__}: {str(exc)[:300]}")
        return 1
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"[成功] 網站回覆: ok={answer.get('ok')} transport={answer.get('transport')}")
    print(f"       網站記錄的時間: {answer.get('lastSeen')}（本機現在 UTC: {now}）")
    print("請現在到網站「Worker / Job 狀態」按「↻ 立即更新」，看 AI Worker 有沒有出現。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
