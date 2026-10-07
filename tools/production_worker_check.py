#!/usr/bin/env python3
"""Authenticated, read-only production check: are the hospital Workers connected?

The anonymous smoke probe (``production_smoke.py``) proves the Web service is
healthy.  It cannot see the Workers, so "Web is green but nothing is processed"
stayed invisible.  This check signs in with a dedicated monitoring account and
reads the same status APIs the admin UI uses:

* ``GET /api/material-jobs``      -> Material Worker heartbeat / version state
* ``GET /api/media-audio/status`` -> AI Worker heartbeat, queues, Kokoro, code identity

Policy
------
* No ``TEACHER_SMOKE_USERNAME``/``TEACHER_SMOKE_PASSWORD``: skipped (exit 0).
* Worker problems are GitHub ``::warning::`` annotations by default so a PC that
  is switched off at night does not fail every 15 minutes.  Set the repository
  variable ``SMOKE_REQUIRE_WORKERS=true`` (or ``--require-workers``) to make
  them fail the run.
* A broken monitoring account / missing permission always fails: that is a
  monitoring configuration error, not a Worker outage.

The account needs only read access to those two endpoints (material
management); never give it more privileges than that.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from prod_client import ApiError, ProductionClient  # noqa: E402

REPORT_PATH = Path("production-worker-report.json")
BAD_VERSION_STATES = {"version_mismatch", "commit_differs"}


def evaluate(jobs: dict[str, Any], audio: dict[str, Any]) -> dict[str, Any]:
    """Turn the two status payloads into ``problems`` / ``warnings`` (pure, testable)."""
    problems: list[str] = []
    warnings: list[str] = []

    workers = [w for w in (jobs.get("workers") or []) if isinstance(w, dict)]
    online = [w for w in workers if w.get("status") in {"online", "busy"}]
    if jobs.get("workerStatusAvailable") is False:
        warnings.append("網站無法讀取 Worker 心跳狀態（資料庫或 heartbeat table 問題）。")
    elif not workers:
        problems.append("Material Worker：從未收到心跳（尚未啟動或 token／網址不對）。")
    elif not online:
        latest = max((str(w.get("lastSeen") or "") for w in workers), default="")
        problems.append(f"Material Worker 離線（最後心跳 {latest or '未知'}）。")
    for worker in online:
        if worker.get("siteVersionState") in BAD_VERSION_STATES:
            warnings.append(f"Material Worker {worker.get('workerId')}：{worker.get('siteVersionMessage') or '程式版本與網站不一致'}")
        if worker.get("updateAvailable"):
            warnings.append(f"Material Worker {worker.get('workerId')} 有新版待更新。")
    for issue in jobs.get("operationalIssues") or []:
        if isinstance(issue, dict) and issue.get("code") in {"WORKER_JOB_STALLED"}:
            warnings.append(str(issue.get("message") or issue.get("code")))
    if int(jobs.get("pendingJobs") or 0) > 0 and int(jobs.get("oldestPendingAgeSeconds") or 0) > 1800 and online:
        warnings.append(f"有教材排隊超過 30 分鐘（{jobs.get('oldestPendingAgeSeconds')} 秒），Worker 在線但沒有領取。")

    worker = audio.get("worker") if isinstance(audio.get("worker"), dict) else {}
    if not worker.get("online"):
        problems.append(f"AI Worker 離線：{str(worker.get('diagnosticMessage') or (audio.get('diagnostic') or {}).get('message') or '')[:160]}")
    else:
        if "media_audio" not in set(worker.get("queues") or []):
            problems.append("AI Worker 在線但沒有回報 media_audio 佇列（程式版本過舊？）。")
        if worker.get("kokoroInstalled") is not True:
            problems.append("AI Worker 回報 Kokoro 未就緒。")
        if worker.get("codeIdentityMatch") is False:
            warnings.append("AI Worker 程式版本與網站不一致，請更新院內 Worker。")
    if not audio.get("providerReady", True):
        problems.append("網站的 AI_TTS_PROVIDER 未設定為 Kokoro。")
    if audio.get("r2Ready") is False:
        problems.append("網站的 R2 尚未設定完成（AI 語音/影片無法使用）。")
    if not problems and audio.get("readyForPreview") is False:
        problems.append(f"AI 語音試聽尚未就緒：{str((audio.get('diagnostic') or {}).get('message') or '')[:160]}")

    return {
        "problems": problems,
        "warnings": warnings,
        "materialWorkersOnline": len(online),
        "materialWorkersSeen": len(workers),
        "aiWorkerOnline": bool(worker.get("online")),
        "aiWorkerKokoro": worker.get("kokoroInstalled"),
        "aiWorkerHeartbeatAgeSeconds": worker.get("heartbeatAgeSeconds"),
        "readyForPreview": audio.get("readyForPreview"),
    }


def run(base_url: str, username: str, password: str) -> dict[str, Any]:
    client = ProductionClient(base_url)
    client.login(username, password)
    try:
        jobs = client.json("GET", "/api/material-jobs?limit=1")
        audio = client.json("GET", "/api/media-audio/status")
    except ApiError as exc:
        if exc.status in {401, 403}:
            raise ApiError("監控帳號沒有讀取 Worker 狀態的權限（需要教材管理權限）。", status=exc.status) from None
        raise
    result = evaluate(jobs, audio)
    result["baseUrl"] = base_url.rstrip("/")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--require-workers", action="store_true", default=os.environ.get("SMOKE_REQUIRE_WORKERS", "").strip().lower() in {"1", "true", "yes", "on"})
    args = parser.parse_args(argv)

    username = os.environ.get("TEACHER_SMOKE_USERNAME", "").strip()
    password = os.environ.get("TEACHER_SMOKE_PASSWORD", "")
    if not username or not password:
        report = {"ok": True, "skipped": True, "reason": "TEACHER_SMOKE_USERNAME/PASSWORD 未設定"}
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("[worker-check] skipped: 未設定 TEACHER_SMOKE_USERNAME / TEACHER_SMOKE_PASSWORD（Worker 在線檢查已略過）")
        return 0

    try:
        report = run(args.base_url, username, password)
    except ApiError as exc:
        report = {"ok": False, "stage": "monitor-account", "error": str(exc)}
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"::error::Worker check failed: {exc}")
        return 1

    report["requireWorkers"] = bool(args.require_workers)
    report["ok"] = not report["problems"] or not args.require_workers
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for message in report["problems"]:
        print(f"::{'error' if args.require_workers else 'warning'}::{message}")
    for message in report["warnings"]:
        print(f"::warning::{message}")
    print(
        f"[worker-check] materialOnline={report['materialWorkersOnline']} aiOnline={report['aiWorkerOnline']} "
        f"kokoro={report['aiWorkerKokoro']} problems={len(report['problems'])} warnings={len(report['warnings'])}"
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
