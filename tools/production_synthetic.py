#!/usr/bin/env python3
"""Production synthetic transaction: prove the real chain works end to end.

CI proves the components connect with stubs; the anonymous smoke probe proves the
Web service is up.  Neither proves that, right now, the production Web service,
Supabase, R2 and the hospital Workers are actually connected.  This script runs a
tiny, clearly labelled transaction with a dedicated account:

1. login + Worker readiness (Material Worker online, AI Worker + Kokoro ready)
2. TTS preview round trip: request -> (AI Worker if not cached) -> R2 -> signed
   URL -> download a real WAV.  A cached preview only proves Web -> R2; that is
   reported as ``viaWorker: false`` (previews are cached permanently, so the AI
   Worker queue itself is covered by step 1's heartbeat/queue/Kokoro state).
3. Material round trip: direct R2 upload -> Material Worker publishes -> the new
   job completes -> the test material is deleted.
   The test material is uploaded as authoring-only (never shown to learners)
   and is skipped entirely when the workers are offline.

Everything is prefixed ``E2E-TEST-`` and cleaned up.  No secret is printed.
Skipped (exit 0) when ``TEACHER_SYNTHETIC_USERNAME``/``PASSWORD`` are absent.
The account needs material management permission in one group and nothing more.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(1, str(Path(__file__).resolve().parents[1]))

from prod_client import ApiError, ProductionClient  # noqa: E402
from production_worker_check import evaluate  # noqa: E402
from teacher_app.common import quiet_hours  # noqa: E402

# Workers stop heartbeats during the overnight quiet window; give them a few
# minutes after it ends to reconnect before calling them offline.
QUIET_GRACE_MINUTES = 15

REPORT_PATH = Path("production-synthetic-report.json")
PREFIX = "E2E-TEST-"


class Report:
    def __init__(self) -> None:
        self.steps: list[dict[str, Any]] = []
        self.ok = True

    def step(self, name: str, fn: Callable[[], dict[str, Any] | None]) -> dict[str, Any] | None:
        started = time.monotonic()
        try:
            detail = fn() or {}
            self.steps.append({"name": name, "ok": True, "seconds": round(time.monotonic() - started, 2), **detail})
            print(f"[synthetic] OK   {name} ({round(time.monotonic() - started, 1)}s) {json.dumps(detail, ensure_ascii=False)[:200]}", flush=True)
            return detail
        except Exception as exc:  # noqa: BLE001 - report every failure with its stage
            self.ok = False
            message = f"{type(exc).__name__}: {str(exc)[:300]}"
            self.steps.append({"name": name, "ok": False, "seconds": round(time.monotonic() - started, 2), "error": message})
            print(f"[synthetic] FAIL {name}: {message}", flush=True)
            print(f"::error::Synthetic step failed: {name}: {message}", flush=True)
            return None


def _readiness(client: ProductionClient) -> dict[str, Any]:
    jobs = client.json("GET", "/api/material-jobs?limit=1")
    audio = client.json("GET", "/api/media-audio/status")
    result = evaluate(jobs, audio)
    if result["problems"]:
        raise RuntimeError("; ".join(result["problems"])[:400])
    for warning in result["warnings"]:
        print(f"::warning::{warning}", flush=True)
    return {"materialWorkersOnline": result["materialWorkersOnline"], "aiWorkerKokoro": result["aiWorkerKokoro"], "warnings": len(result["warnings"])}


def _check_wav(client: ProductionClient, url: str) -> int:
    # The presigned R2 URL carries its own signature: never send our session cookie.
    status, _headers, body = client.request("GET", url, send_cookies=False, timeout=60)
    if status != 200:
        raise RuntimeError(f"下載預覽音檔失敗 HTTP {status}")
    if len(body) < 2048 or body[:4] != b"RIFF" or body[8:12] != b"WAVE":
        raise RuntimeError(f"預覽音檔不是有效的 WAV（{len(body)} bytes）")
    return len(body)


def tts_roundtrip(client: ProductionClient, *, voice: str, timeout_seconds: int) -> dict[str, Any]:
    data = client.json("POST", "/api/media-audio/preview", json_body={"voice": voice}, expected=(200, 202))
    via_worker = bool(data.get("jobId"))
    deadline = time.monotonic() + timeout_seconds
    while data.get("status") not in {"completed", "failed"}:
        if time.monotonic() > deadline:
            raise RuntimeError(f"AI 語音工作逾時（{timeout_seconds} 秒），狀態 {data.get('status')}：AI Worker 可能沒有領取工作。")
        time.sleep(3)
        data = client.json("GET", f"/api/media-audio/jobs/{data['jobId']}")
    if data.get("status") == "failed":
        raise RuntimeError(f"AI 語音工作失敗：{str(data.get('error') or '')[:200]}")
    result = data.get("result") or {}
    url = str(result.get("previewUrl") or "")
    if not url:
        raise RuntimeError("AI 語音工作完成，但沒有試聽網址（R2 簽名網址失敗？）")
    size = _check_wav(client, url)
    return {"voice": result.get("voice") or voice, "viaWorker": via_worker, "replayed": bool(result.get("replayed")), "wavBytes": size}


def material_roundtrip(client: ProductionClient, user: dict[str, Any], *, group: str, timeout_seconds: int) -> dict[str, Any]:
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    title = f"{PREFIX}{stamp}"
    content = f"Teacher production synthetic material {stamp}\n".encode("utf-8")
    sha = hashlib.sha256(content).hexdigest()
    group = group or str(user.get("preferredGroup") or "")
    material_id = ""
    try:
        status, _h, body = client.request(
            "POST",
            "/api/material-upload/init",
            json_body={"filename": f"{title}.txt", "size": len(content), "sha256": sha, "title": title, "desc": "Automated synthetic check; safe to delete.", "group": group, "area": "internal", "materialType": "standard", "authoringOnly": True},
        )
        init = json.loads(body.decode("utf-8", errors="replace") or "{}")
        if status == 409 and init.get("available") is False:
            return {"skipped": True, "reason": "網站未啟用 R2 直傳（略過教材來回檢查）"}
        if status != 201:
            raise RuntimeError(f"建立上傳工作失敗 HTTP {status}: {str(init.get('error') or '')[:200]}")
        material_id = str(init.get("materialId") or "")
        if init.get("mode") != "single" or not init.get("url"):
            raise RuntimeError(f"非預期的上傳模式：{init.get('mode')}")
        put_status, put_headers, _ = client.request("PUT", str(init["url"]), data=content, send_cookies=False, headers={"Content-Type": "application/octet-stream"}, timeout=60)
        if put_status not in {200, 204}:
            raise RuntimeError(f"上傳到 R2 失敗 HTTP {put_status}（檢查 R2 憑證／CORS／簽名）")
        etag = put_headers.get("etag", "")
        complete = client.json("POST", f"/api/material-upload/{init['uploadId']}/complete", json_body={"parts": [{"partNumber": 1, "etag": etag, "sha256": sha}]}, expected=(200, 201, 202))
        queued_at = time.monotonic()
        if not complete.get("jobId"):
            raise RuntimeError(f"完成上傳後沒有 jobId：{json.dumps(complete, ensure_ascii=False)[:200]}")
        job_id = str(complete["jobId"])
        deadline = queued_at + timeout_seconds
        job: dict[str, Any] = {}
        while time.monotonic() < deadline:
            job = client.json("GET", f"/api/material-jobs/{job_id}", expected=(200,))
            status_value = str(job.get("status") or "")
            if status_value == "completed":
                break
            if status_value in {"failed", "cancelled"}:
                raise RuntimeError(f"Material Worker 處理測試教材失敗（{status_value}）。")
            print(f"[synthetic] 等待教材處理中…狀態 {status_value or '未知'}（已等 {round(time.monotonic() - queued_at)} 秒）", flush=True)
            time.sleep(5)
        else:
            raise RuntimeError(f"教材 {timeout_seconds} 秒內沒有處理完成：Material Worker 可能沒有領取或處理失敗。")
        return {"materialId": material_id, "queuedToVisibleSeconds": round(time.monotonic() - queued_at, 1), "authoringOnly": True}
    finally:
        if material_id:
            try:
                client.json("DELETE", f"/api/slides/{material_id}", expected=(200, 202, 404))
                print(f"[synthetic] cleaned up test material {material_id}", flush=True)
            except Exception as exc:  # noqa: BLE001
                print(f"::warning::無法自動刪除測試教材 {material_id}（{type(exc).__name__}）；請在教材管理手動刪除 {PREFIX}*。", flush=True)


def run(base_url: str, username: str, password: str, *, group: str, voice: str, skip_tts: bool, skip_material: bool, timeout_seconds: int, max_total_seconds: int = 600) -> Report:
    report = Report()
    run_deadline = time.monotonic() + max_total_seconds

    def budget(name: str) -> int:
        """Per-step wait, capped by what is left of the whole run's time budget."""
        remaining = int(run_deadline - time.monotonic())
        if remaining < 30:
            raise RuntimeError(f"整體檢查已超過 {max_total_seconds} 秒上限，略過 {name}（避免一直卡住）。")
        return min(timeout_seconds, remaining)

    client = ProductionClient(base_url)
    user_holder: dict[str, Any] = {}

    def login() -> dict[str, Any]:
        user_holder.update(client.login(username, password))
        return {"role": user_holder.get("role"), "group": user_holder.get("preferredGroup")}

    if report.step("login", login) is None:
        return report
    if quiet_hours.in_quiet_hours(default=quiet_hours.DEFAULT_WORKER_QUIET_HOURS, grace_minutes=QUIET_GRACE_MINUTES):
        # Workers are paused on purpose overnight; that is not an outage.
        print("[synthetic] SKIP worker checks：夜間靜音時段（Worker 刻意暫停），不判定為離線。", flush=True)
        return report
    workers_ready = report.step("worker-readiness", lambda: _readiness(client)) is not None
    if not skip_tts:
        report.step("tts-roundtrip", lambda: tts_roundtrip(client, voice=voice, timeout_seconds=budget("tts-roundtrip")))
    if not skip_material and not workers_ready:
        # Workers offline: uploading would only leave a stuck/failed E2E-TEST job behind.
        print("[synthetic] SKIP material-roundtrip：Worker 離線，不上傳測試教材。", flush=True)
    elif not skip_material:
        report.step("material-roundtrip", lambda: material_roundtrip(client, user_holder, group=group, timeout_seconds=budget("material-roundtrip")))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--voice", default=os.environ.get("TEACHER_SYNTHETIC_VOICE", "zf_001"))
    parser.add_argument("--group", default=os.environ.get("TEACHER_SYNTHETIC_GROUP", ""))
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--max-total-seconds", type=int, default=600, help="whole-run time budget so the job never hangs for long")
    parser.add_argument("--skip-tts", action="store_true")
    parser.add_argument("--skip-material", action="store_true")
    args = parser.parse_args(argv)

    username = os.environ.get("TEACHER_SYNTHETIC_USERNAME", "").strip()
    password = os.environ.get("TEACHER_SYNTHETIC_PASSWORD", "")
    if not username or not password:
        REPORT_PATH.write_text(json.dumps({"ok": True, "skipped": True, "reason": "TEACHER_SYNTHETIC_USERNAME/PASSWORD 未設定"}, ensure_ascii=False, indent=2), encoding="utf-8")
        print("[synthetic] skipped: 未設定 TEACHER_SYNTHETIC_USERNAME / TEACHER_SYNTHETIC_PASSWORD")
        return 0

    try:
        report = run(args.base_url, username, password, group=args.group, voice=args.voice, skip_tts=args.skip_tts, skip_material=args.skip_material, timeout_seconds=args.timeout_seconds, max_total_seconds=args.max_total_seconds)
    except ApiError as exc:
        REPORT_PATH.write_text(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"::error::Synthetic check failed: {exc}")
        return 1
    payload = {"ok": report.ok, "baseUrl": args.base_url.rstrip("/"), "steps": report.steps}
    REPORT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
