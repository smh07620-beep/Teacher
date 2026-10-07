"""Worker self-diagnosis: "does this Worker PC actually connect to everything?".

The CI end-to-end suites prove the components work together with stubs.  They
cannot prove that THIS Windows host has the right URL/token, matching code,
working R2 credentials, LibreOffice/FFmpeg and a real Kokoro voice.  Each check
here verifies one link of that chain and reports a concrete next step.

Usage (from the Worker checkout):  ``python worker_doctor.py [--quick] [--json]``

No secret value is ever printed.  Network probes use only read-only or
rejected-by-design requests (no job is claimed, no worker heartbeat row is
created).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from teacher_app.worker import site_check

ROOT = Path(__file__).resolve().parents[2]
OK, WARN, FAIL, SKIP = "ok", "warn", "fail", "skip"
_ENV_LINE = re.compile(r"^\s*([^#=\s]+)\s*=\s*(.*?)\s*$")
_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


@dataclass
class Check:
    name: str
    status: str
    detail: str = ""
    hint: str = ""
    seconds: float = 0.0


def load_env_file(path: Path, environ: dict[str, str] | None = None) -> int:
    """Load ``.local-worker.env`` exactly like the PowerShell supervisors do."""
    environ = os.environ if environ is None else environ
    path = Path(path)
    if not path.is_file():
        return 0
    count = 0
    # utf-8-sig: Notepad / PowerShell often save a BOM; PowerShell's Get-Content
    # strips it, so the doctor must too or the first key (e.g. TEACHER_BASE_URL)
    # is misread as missing.
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        match = _ENV_LINE.match(line)
        if match:
            environ[match.group(1)] = match.group(2)
            count += 1
    return count


def _truthy(value: str | None, default: bool = False) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return default
    return text not in {"0", "false", "no", "off"}


def default_http(method: str, url: str, *, headers: dict[str, str] | None = None, body: bytes | None = None, timeout: float = 15.0) -> tuple[int, str]:
    """Tiny stdlib HTTP helper -> ``(status, text)``; ``(0, error)`` on network failure."""
    request = Request(url, data=body, method=method, headers=headers or {})
    try:
        with urlopen(request, timeout=timeout) as response:
            return int(getattr(response, "status", 200) or 200), response.read(65536).decode("utf-8", errors="replace")
    except HTTPError as exc:
        try:
            text = exc.read(65536).decode("utf-8", errors="replace")
        except Exception:
            text = ""
        return int(exc.code), text
    except (URLError, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", exc)
        return 0, f"{type(exc).__name__}: {str(reason)[:160]}"


class Doctor:
    def __init__(
        self,
        env: dict[str, str] | None = None,
        *,
        http: Callable[..., tuple[int, str]] = default_http,
        quick: bool = False,
        root: Path | None = None,
    ) -> None:
        self.env = os.environ if env is None else env
        self.http = http
        self.quick = quick
        self.root = Path(root or ROOT)
        self.results: list[Check] = []

    # ------------------------------------------------------------------ helpers
    def _base_url(self) -> str:
        return str(self.env.get("TEACHER_BASE_URL") or "").strip().rstrip("/")

    def _material_token(self) -> str:
        return str(self.env.get("MATERIAL_WORKER_TOKEN") or "").strip()

    def _ai_token(self) -> str:
        return str(self.env.get("AI_WORKER_TOKEN") or self.env.get("MATERIAL_WORKER_TOKEN") or "").strip()

    def _add(self, name: str, status: str, detail: str = "", hint: str = "", started: float | None = None) -> Check:
        item = Check(name, status, detail, hint, round(time.monotonic() - started, 2) if started else 0.0)
        self.results.append(item)
        return item

    # ------------------------------------------------------------------ checks
    def check_config(self) -> None:
        base = self._base_url()
        problems, notes = [], []
        if not base:
            problems.append("TEACHER_BASE_URL 未設定")
        else:
            parts = urlsplit(base)
            loopback_ok = parts.hostname in _LOOPBACK and _truthy(self.env.get("MATERIAL_WORKER_ALLOW_INSECURE_LOCALHOST"))
            if parts.scheme != "https" and not loopback_ok:
                problems.append("TEACHER_BASE_URL 必須是 https://（僅測試可允許本機 http）")
            notes.append(parts.hostname or "")
        if not self._material_token():
            problems.append("MATERIAL_WORKER_TOKEN 未設定")
        if not str(self.env.get("MATERIAL_WORKER_ID") or "").strip():
            notes.append("未設定固定 MATERIAL_WORKER_ID（建議設定，重啟後狀態才不會變成新 Worker）")
        if problems:
            self._add("設定檔", FAIL, "；".join(problems), "編輯 .local-worker.env 後重新執行；範例見 .local-worker.env.example")
        else:
            self._add("設定檔", WARN if any("MATERIAL_WORKER_ID" in n for n in notes) else OK, "；".join(n for n in notes if n) or "必要設定齊全")

    def check_site(self) -> bool:
        started = time.monotonic()
        base = self._base_url()
        if not base:
            self._add("網站連線", SKIP, "沒有 TEACHER_BASE_URL")
            return False
        health = site_check.fetch_site_health(base, timeout=15.0)
        payload = health.get("payload") or {}
        if not payload:
            self._add(
                "網站連線",
                FAIL,
                str(health.get("error") or "沒有回應"),
                "確認這台電腦能以 HTTPS 443 連到網站（防火牆／Proxy／DNS）；Render 免費方案休眠時第一次請求可能需要 1–2 分鐘，可重試。",
                started,
            )
            return False
        version = payload.get("version") or "?"
        db = (payload.get("database") or {}).get("kind") or "?"
        if health.get("ok") and payload.get("ok") is True:
            self._add("網站連線", OK, f"網站 {version}，資料庫 {db}", started=started)
        else:
            self._add("網站連線", WARN, f"HTTP {health.get('status')}，status={payload.get('status')}", "網站可達但回報不健康；請查看 Render 日誌。", started)
        return True

    def _probe_token(self, name: str, *, method: str, path: str, token: str, headers: dict[str, str], body: bytes | None, ok_hint: str) -> None:
        started = time.monotonic()
        base = self._base_url()
        if not base or not token:
            self._add(name, SKIP, "缺少 TEACHER_BASE_URL 或 token")
            return
        status, text = self.http(method, base + path, headers={"Authorization": f"Bearer {token}", **headers}, body=body, timeout=20.0)
        if status == 0:
            self._add(name, FAIL, text, "網站無法連線；請先處理「網站連線」。", started)
        elif status == 401:
            self._add(name, FAIL, "網站拒絕這個 token（401）", ok_hint, started)
        elif status == 429:
            self._add(name, WARN, "Worker API 暫時被限流（429），token 可能正確", "稍後重試。", started)
        elif status >= 500:
            self._add(name, WARN, f"網站錯誤 HTTP {status}", "查看 Render 日誌；這不一定是 token 問題。", started)
        else:
            self._add(name, OK, f"token 被網站接受（HTTP {status}）", started=started)

    def check_tokens(self) -> None:
        worker_id = str(self.env.get("MATERIAL_WORKER_ID") or "doctor-probe")[:60]
        # An unknown job id: auth is evaluated first, then the lookup rejects the
        # request.  Nothing is claimed, created or modified.
        self._probe_token(
            "Material Worker token",
            method="GET",
            path="/api/material-worker/doctor-probe/source",
            token=self._material_token(),
            headers={"X-Teacher-Worker-Id": worker_id},
            body=None,
            ok_hint="MATERIAL_WORKER_TOKEN 與 Render 上的設定不一致；請兩邊改成同一個值。",
        )
        # An empty RPC body is rejected with HTTP 400 after the token check.
        self._probe_token(
            "AI Worker token",
            method="POST",
            path="/api/ai-worker/rpc",
            token=self._ai_token(),
            headers={"Content-Type": "application/json"},
            body=b"{}",
            ok_hint="AI_WORKER_TOKEN（或 MATERIAL_WORKER_TOKEN）與 Render 上的設定不一致。",
        )

    def check_version(self) -> None:
        started = time.monotonic()
        base = self._base_url()
        if not base:
            self._add("程式版本", SKIP, "沒有 TEACHER_BASE_URL")
            return
        result = site_check.check(base, root=self.root, timeout=15.0)
        state = result.get("state")
        if state == site_check.STATE_MATCH:
            self._add("程式版本", OK, str(result.get("message") or ""), started=started)
        elif state in site_check.NEEDS_UPDATE_STATES:
            self._add("程式版本", WARN, str(result.get("message") or ""), "在這台電腦更新程式（git pull 或 update_material_worker.ps1）後重新啟動 Worker。", started)
        else:
            self._add("程式版本", WARN, str(result.get("message") or ""), started=started)

    def _binary(self, env_name: str, command: str, version_args: list[str]) -> tuple[str, str]:
        configured = str(self.env.get(env_name) or "").strip()
        path = configured or shutil.which(command) or ""
        if not path and command == "soffice":
            try:
                from teacher_app.materials import ai_video_renderer

                path = ai_video_renderer._libreoffice()
            except Exception:
                path = ""
        if not path:
            return "", "找不到執行檔"
        try:
            completed = subprocess.run([path, *version_args], capture_output=True, timeout=30, check=False)
        except subprocess.TimeoutExpired:
            return path, "執行逾時（30 秒）"
        except OSError as exc:
            return path, f"無法執行：{type(exc).__name__}"
        if completed.returncode != 0:
            return path, f"回傳碼 {completed.returncode}"
        first = (completed.stdout or completed.stderr or b"").decode("utf-8", errors="replace").strip().splitlines()
        return path, (first[0][:80] if first else "ok")

    def check_binaries(self) -> None:
        for label, env_name, command, args, required in (
            ("FFmpeg", "FFMPEG_PATH", "ffmpeg", ["-version"], True),
            ("FFprobe", "FFPROBE_PATH", "ffprobe", ["-version"], False),
            ("LibreOffice", "SOFFICE_PATH", "soffice", ["--version"], True),
        ):
            started = time.monotonic()
            path, detail = self._binary(env_name, command, args)
            hint = f"安裝 {label}，或在 .local-worker.env 設定 {env_name}=完整路徑"
            if path and detail not in {"找不到執行檔"} and not detail.startswith(("執行逾時", "無法執行", "回傳碼")):
                self._add(label, OK, detail, started=started)
            else:
                self._add(label, FAIL if required else WARN, detail, hint, started)

    def check_storage(self) -> None:
        started = time.monotonic()
        try:
            from teacher_app.storage.worker_runtime import WorkerMaterialStorageAdapter

            result = WorkerMaterialStorageAdapter().startup_preflight()
        except Exception as exc:  # report the cause, never a traceback with secrets
            self._add("教材儲存", FAIL, f"{type(exc).__name__}: {str(exc)[:200]}", "檢查 MATERIAL_STORAGE_BACKEND 與對應的 MEGA／Google Drive／R2 設定。", started)
            return
        if result.get("ready"):
            self._add("教材儲存", OK, f"{result.get('backend')}：{result.get('detail')}", started=started)
        else:
            self._add("教材儲存", FAIL, str(result.get("detail") or "preflight 未通過"), started=started)

    def check_r2(self) -> None:
        started = time.monotonic()
        try:
            from teacher_app.storage import providers
        except Exception as exc:
            self._add("R2 讀寫", FAIL, f"無法載入儲存模組：{type(exc).__name__}", "請在 Worker 的 .venv 內執行（缺少 boto3 等套件）。", started)
            return
        if not providers.r2_is_configured():
            self._add("R2 讀寫", WARN, "R2 尚未設定", "AI 語音／影片需要 R2；設定 R2_* 變數。", started)
            return
        key = f"doctor/{re.sub(r'[^A-Za-z0-9._-]', '-', socket.gethostname())[:40]}-{uuid.uuid4().hex[:8]}.txt"
        try:
            client = providers.r2_client()
            bucket = providers.R2_BUCKET_NAME
            client.put_object(Bucket=bucket, Key=key, Body=b"teacher-worker-doctor\n")
            head = client.head_object(Bucket=bucket, Key=key)
            size = int(head.get("ContentLength") or 0)
        except Exception as exc:
            self._add("R2 讀寫", FAIL, f"{type(exc).__name__}: {str(exc)[:200]}", "檢查 R2_ACCESS_KEY_ID／SECRET／ENDPOINT／BUCKET，以及該金鑰是否有寫入權限。", started)
            return
        try:
            client.delete_object(Bucket=bucket, Key=key)
        except Exception as exc:
            self._add("R2 讀寫", WARN, f"寫入成功但刪除失敗（{type(exc).__name__}）", f"請手動刪除 {key}；金鑰可能缺少刪除權限。", started)
            return
        self._add("R2 讀寫", OK, f"寫入／讀取／刪除成功（{size} bytes）", started=started)

    def check_libreoffice_convert(self) -> None:
        if self.quick:
            self._add("LibreOffice 轉檔", SKIP, "--quick 略過")
            return
        started = time.monotonic()
        try:
            from teacher_app.storage.worker_runtime import WorkerMaterialStorageAdapter

            adapter = WorkerMaterialStorageAdapter()
            status = adapter.warmup_libreoffice()
        except Exception as exc:
            self._add("LibreOffice 轉檔", FAIL, f"{type(exc).__name__}: {str(exc)[:200]}", started=started)
            return
        try:
            if status.get("warmed"):
                self._add("LibreOffice 轉檔", OK, f"預熱轉檔成功，耗時 {status.get('warmupSeconds')} 秒", started=started)
            else:
                self._add("LibreOffice 轉檔", FAIL, str(status.get("lastError") or "預熱轉檔失敗"), "確認 LibreOffice 可獨立開啟；必要時關閉 MATERIAL_LIBREOFFICE_WARM_ENABLED 以走單次轉檔。", started)
        finally:
            try:
                adapter._libreoffice_warm.close()
            except Exception:
                pass

    def check_kokoro(self) -> None:
        if self.quick:
            self._add("Kokoro 語音", SKIP, "--quick 略過（完整檢查會合成一句話）")
            return
        started = time.monotonic()
        try:
            from teacher_app.materials import media_audio_runtime

            state = media_audio_runtime.preload_kokoro()
            repo = media_audio_runtime._repo_id()
            missing = [v for v in sorted(media_audio_runtime.ALLOWED_VOICES) if not media_audio_runtime._kokoro_assets_cached(repo, v)]
        except Exception as exc:
            self._add("Kokoro 語音", FAIL, f"{type(exc).__name__}: {str(exc)[:200]}", "確認已安裝 requirements-ai-worker.txt，且第一次執行時可連網下載模型。", started)
            return
        timings = state.get("timings") or {}
        detail = f"預設聲音 {state.get('voice')} 合成成功，總耗時 {timings.get('total', '?')} 秒"
        if missing:
            self._add("Kokoro 語音", WARN, detail + f"；尚未快取的聲音：{', '.join(missing)}（第一次使用時會下載）", started=started)
        else:
            self._add("Kokoro 語音", OK, detail, started=started)

    # ------------------------------------------------------------------ driver
    def run(self) -> list[Check]:
        self.results = []
        self.check_config()
        site_ok = self.check_site()
        if site_ok:
            self.check_tokens()
            self.check_version()
        else:
            for name in ("Material Worker token", "AI Worker token", "程式版本"):
                self._add(name, SKIP, "網站無法連線，略過")
        self.check_binaries()
        self.check_storage()
        self.check_r2()
        self.check_libreoffice_convert()
        self.check_kokoro()
        return self.results

    @staticmethod
    def exit_code(results: list[Check]) -> int:
        return 1 if any(item.status == FAIL for item in results) else 0


_ICON = {OK: "[ OK ]", WARN: "[WARN]", FAIL: "[FAIL]", SKIP: "[SKIP]"}


def format_report(results: list[Check]) -> str:
    lines = []
    for item in results:
        suffix = f" ({item.seconds}s)" if item.seconds >= 1 else ""
        lines.append(f"{_ICON.get(item.status, '[ ?? ]')} {item.name}: {item.detail}{suffix}")
        if item.hint and item.status in {WARN, FAIL}:
            lines.append(f"        → {item.hint}")
    fails = sum(i.status == FAIL for i in results)
    warns = sum(i.status == WARN for i in results)
    lines.append("")
    lines.append(f"結果：{'有問題，請依上方提示處理' if fails else '全部通過' if not warns else '可運作，但有建議事項'}（失敗 {fails}、警告 {warns}）")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Teacher Worker 自我診斷（不會輸出任何密碼或 token）")
    parser.add_argument("--env-file", default=str(ROOT / ".local-worker.env"), help="預設為 Worker 目錄下的 .local-worker.env")
    parser.add_argument("--quick", action="store_true", help="略過 LibreOffice 預熱轉檔與 Kokoro 合成（較快）")
    parser.add_argument("--json", action="store_true", help="以 JSON 輸出")
    args = parser.parse_args(argv)
    loaded = load_env_file(Path(args.env_file))
    if not args.json:
        print(f"Teacher Worker 診斷（已載入 {loaded} 項設定，來源 {Path(args.env_file).name}）\n")
    results = Doctor(quick=args.quick).run()
    if args.json:
        print(json.dumps([asdict(item) for item in results], ensure_ascii=False, indent=2))
    else:
        print(format_report(results))
    return Doctor.exit_code(results)


__all__ = ["Check", "Doctor", "format_report", "load_env_file", "main"]
