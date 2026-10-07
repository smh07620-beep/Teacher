"""Compare the local Worker checkout with the deployed Web service.

A Worker that silently runs older code than the Web service is the most common
reason "every feature exists but they do not connect" (for example a Web UI that
offers a voice the old Worker cannot synthesize).  This module is deliberately
stdlib-only and side-effect free so the Material Worker, the AI Worker and
``worker_doctor.py`` can all share it.

The result is informational: normal Web releases must not force the hospital
Worker to update (see ``protocol_version.py`` for the only hard gate).  The
Worker logs a clear message and publishes the state in its heartbeat so the
operator sees it in the Worker status panel.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]

STATE_MATCH = "match"
STATE_VERSION_MISMATCH = "version_mismatch"
STATE_COMMIT_DIFFERS = "commit_differs"
STATE_UNKNOWN = "unknown"
STATE_SITE_UNREACHABLE = "site_unreachable"

#: States that mean "the operator should update this Worker".
NEEDS_UPDATE_STATES = frozenset({STATE_VERSION_MISMATCH, STATE_COMMIT_DIFFERS})


def local_identity(root: Path | None = None) -> dict[str, str]:
    """Return the Worker checkout version and short commit (never raises)."""
    root = Path(root or ROOT)
    try:
        version = (root / "VERSION").read_text(encoding="utf-8").strip()[:32]
    except OSError:
        version = ""
    sha = ""
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if completed.returncode == 0:
            sha = str(completed.stdout or "").strip().lower()[:40]
    except (OSError, subprocess.TimeoutExpired):
        sha = ""
    return {"version": version, "sha": sha}


def fetch_site_health(base_url: str, *, timeout: float = 8.0, opener: Callable[..., Any] = urlopen) -> dict[str, Any]:
    """GET ``/health``.  Returns ``{"ok", "status", "payload", "error"}``; never raises."""
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        return {"ok": False, "status": 0, "payload": {}, "error": "TEACHER_BASE_URL 未設定"}
    request = Request(base + "/health", headers={"Accept": "application/json", "User-Agent": "TeacherWorkerSiteCheck/1.0"})
    try:
        with opener(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200) or 200)
            raw = response.read()
    except HTTPError as exc:
        # A degraded site still returns a JSON health body on 503.
        status = int(exc.code)
        try:
            raw = exc.read()
        except Exception:
            raw = b""
    except (URLError, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", exc)
        return {"ok": False, "status": 0, "payload": {}, "error": f"{type(exc).__name__}: {str(reason)[:160]}"}
    try:
        payload = json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return {"ok": 200 <= status < 300, "status": status, "payload": payload, "error": "" if payload else f"HTTP {status} 沒有 JSON"}


def commits_match(left: str, right: str) -> bool:
    """Prefix match (min 7 chars) so a 7-char and a 12-char short SHA compare equal."""
    left = str(left or "").strip().lower()
    right = str(right or "").strip().lower()
    if len(left) < 7 or len(right) < 7:
        return False
    length = min(len(left), len(right))
    return left[:length] == right[:length]


def compare(local: Mapping[str, str], health: Mapping[str, Any]) -> dict[str, Any]:
    """Classify the local checkout against a ``fetch_site_health`` result."""
    local_version = str(local.get("version") or "")
    local_sha = str(local.get("sha") or "")
    payload = health.get("payload") if isinstance(health.get("payload"), Mapping) else {}
    deployment = payload.get("deployment") if isinstance(payload.get("deployment"), Mapping) else {}
    site_version = str(payload.get("version") or "")
    site_commit = str(deployment.get("commit") or "")
    result: dict[str, Any] = {
        "state": STATE_UNKNOWN,
        "message": "",
        "localVersion": local_version,
        "localSha": local_sha,
        "siteVersion": site_version,
        "siteCommit": site_commit,
    }
    if not payload:
        result["state"] = STATE_SITE_UNREACHABLE
        result["message"] = f"無法讀取網站版本（{str(health.get('error') or '未知原因')[:120]}）；請確認 TEACHER_BASE_URL 與網路。"
        return result
    if local_version and site_version and local_version != site_version:
        result["state"] = STATE_VERSION_MISMATCH
        result["message"] = (
            f"Worker 版本 {local_version} 與網站 {site_version} 不同；"
            "請更新院內 Worker（git pull 或更新腳本）後重新啟動。"
        )
        return result
    if local_sha and site_commit:
        if commits_match(local_sha, site_commit):
            result["state"] = STATE_MATCH
            result["message"] = f"Worker 與網站程式一致（{local_sha[:7]}）。"
        else:
            result["state"] = STATE_COMMIT_DIFFERS
            result["message"] = (
                f"Worker 程式 {local_sha[:7]} 與網站部署 {site_commit[:7]} 不同（版本號相同）；"
                "若遇到功能對不上，請更新院內 Worker 後重新啟動。"
            )
        return result
    if local_version and site_version:
        result["state"] = STATE_MATCH
        result["message"] = f"Worker 與網站版本號一致（{local_version}）；無法比對 commit。"
        return result
    result["message"] = "資訊不足，無法比對 Worker 與網站版本。"
    return result


def check(base_url: str, *, root: Path | None = None, timeout: float = 8.0, opener: Callable[..., Any] = urlopen) -> dict[str, Any]:
    """One-shot comparison used by ``worker_doctor.py`` and the monitor."""
    return compare(local_identity(root), fetch_site_health(base_url, timeout=timeout, opener=opener))


class SiteVersionMonitor:
    """Cached, thread-safe version check suitable for every heartbeat.

    Heartbeats happen every few seconds, the check only hits ``/health`` every
    ``interval_seconds`` (shorter retry while the site is unreachable) and logs
    once whenever the state changes.
    """

    def __init__(
        self,
        base_url: str | Callable[[], str],
        *,
        interval_seconds: float = 1800.0,
        retry_seconds: float = 300.0,
        log: Callable[[str], None] | None = None,
        checker: Callable[[str], dict[str, Any]] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._base_url = base_url
        self.interval_seconds = max(30.0, float(interval_seconds))
        self.retry_seconds = max(15.0, float(retry_seconds))
        self._log = log
        self._checker = checker or (lambda url: check(url))
        self._clock = clock
        self._lock = threading.Lock()
        self._snapshot: dict[str, Any] = {}
        self._next_check = 0.0
        self._last_state = ""

    def _url(self) -> str:
        return str(self._base_url() if callable(self._base_url) else self._base_url or "")

    def snapshot(self, *, force: bool = False) -> dict[str, Any]:
        with self._lock:
            now = self._clock()
            if force or not self._snapshot or now >= self._next_check:
                try:
                    result = dict(self._checker(self._url()))
                except Exception as exc:  # never break a heartbeat
                    result = {"state": STATE_UNKNOWN, "message": f"版本檢查失敗：{type(exc).__name__}"}
                result["checkedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                self._snapshot = result
                state = str(result.get("state") or STATE_UNKNOWN)
                retry = state in {STATE_SITE_UNREACHABLE, STATE_UNKNOWN}
                self._next_check = now + (self.retry_seconds if retry else self.interval_seconds)
                if state != self._last_state:
                    self._last_state = state
                    if self._log is not None:
                        try:
                            self._log(f"site version check state={state}: {result.get('message', '')}")
                        except Exception:
                            pass
            return dict(self._snapshot)


__all__ = [
    "NEEDS_UPDATE_STATES",
    "STATE_COMMIT_DIFFERS",
    "STATE_MATCH",
    "STATE_SITE_UNREACHABLE",
    "STATE_UNKNOWN",
    "STATE_VERSION_MISMATCH",
    "SiteVersionMonitor",
    "check",
    "commits_match",
    "compare",
    "fetch_site_health",
    "local_identity",
]
