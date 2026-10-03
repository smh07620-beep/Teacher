#!/usr/bin/env python3
"""Read-only production acceptance probe for the deployed Teacher web service."""

from __future__ import annotations

import argparse
import http.client
import json
import socket
import ssl
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = Path("production-smoke-report.json")
USER_AGENT = "TeacherProductionSmoke/1.0"
EXPECTED_VERSION = ROOT.joinpath("VERSION").read_text(encoding="utf-8").strip()
RETRYABLE_HTTP_STATUSES = {502, 503, 504}
DEFAULT_REQUEST_ATTEMPTS = 3
DEFAULT_REQUEST_RETRY_DELAY = 2.0
DEFAULT_REQUEST_TIMEOUT = 30


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: bytes

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.text())


class SmokeCheckError(RuntimeError):
    def __init__(self, stage: str, cause: BaseException):
        self.stage = stage
        self.cause = cause
        super().__init__(f"{stage}: {type(cause).__name__}: {cause}")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: N802
        return None


def _dns_diagnostic(base_url: str) -> dict[str, Any]:
    parsed = urlsplit(base_url)
    host = parsed.hostname
    if not host:
        return {"ok": False, "stage": "url", "error": f"invalid base URL: {base_url!r}"}
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        rows = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        return {
            "ok": False,
            "stage": "dns",
            "host": host,
            "error": f"{type(exc).__name__}: {exc}",
        }
    addresses = sorted({row[4][0] for row in rows})
    return {"ok": True, "stage": "dns", "host": host, "addresses": addresses}


def _commit_matches(observed: str, expected: str) -> bool:
    observed_value = str(observed or "").strip().lower()
    expected_value = str(expected or "").strip().lower()
    common_length = min(len(observed_value), len(expected_value))
    return common_length >= 7 and observed_value[:common_length] == expected_value[:common_length]


def _network_error_stage(exc: BaseException) -> str:
    reason = exc.reason if isinstance(exc, URLError) else exc
    if isinstance(reason, socket.gaierror):
        return "dns"
    if isinstance(reason, ssl.SSLError):
        return "tls"
    if isinstance(reason, (socket.timeout, TimeoutError)):
        return "timeout"
    if isinstance(reason, ConnectionRefusedError):
        return "tcp"
    if isinstance(reason, http.client.HTTPException):
        return "protocol"
    return "http"

def _request(
    base_url: str,
    path: str,
    *,
    follow_redirects: bool = True,
    timeout: int = DEFAULT_REQUEST_TIMEOUT,
    attempts: int = DEFAULT_REQUEST_ATTEMPTS,
    retry_delay: float = DEFAULT_REQUEST_RETRY_DELAY,
) -> Response:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    request = Request(
        url,
        headers={
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
            "User-Agent": USER_AGENT,
            "Cache-Control": "no-cache",
        },
        method="GET",
    )
    opener = build_opener() if follow_redirects else build_opener(NoRedirect)
    total_attempts = max(1, attempts)

    for attempt in range(1, total_attempts + 1):
        try:
            with opener.open(request, timeout=timeout) as response:
                result = Response(
                    status=int(response.getcode() or 0),
                    headers={str(k).lower(): str(v) for k, v in response.headers.items()},
                    body=response.read(),
                )
        except HTTPError as exc:
            try:
                body = exc.read()
            except http.client.HTTPException as read_exc:
                if attempt >= total_attempts:
                    raise
                stage = _network_error_stage(read_exc)
                print(
                    f"[production-smoke] GET {path} failed at stage={stage} "
                    f"(attempt {attempt}/{total_attempts}); retrying: {read_exc}",
                    flush=True,
                )
                time.sleep(max(0.0, retry_delay))
                continue
            result = Response(
                status=int(exc.code or 0),
                headers={str(k).lower(): str(v) for k, v in exc.headers.items()},
                body=body,
            )
        except (URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
            if attempt >= total_attempts:
                raise
            stage = _network_error_stage(exc)
            print(
                f"[production-smoke] GET {path} failed at stage={stage} "
                f"(attempt {attempt}/{total_attempts}); retrying: {exc}",
                flush=True,
            )
            time.sleep(max(0.0, retry_delay))
            continue

        if result.status in RETRYABLE_HTTP_STATUSES and attempt < total_attempts:
            print(
                f"[production-smoke] GET {path} returned HTTP {result.status} "
                f"(attempt {attempt}/{total_attempts}); retrying",
                flush=True,
            )
            time.sleep(max(0.0, retry_delay))
            continue
        return result

    raise AssertionError(f"GET {path} exhausted request attempts without a response")

def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


@contextmanager
def _check_stage(stage: str):
    try:
        yield
    except SmokeCheckError:
        raise
    except Exception as exc:
        raise SmokeCheckError(stage, exc) from exc


def _json_endpoint(base_url: str, path: str, expected_status: int = 200) -> tuple[Response, dict]:
    response = _request(base_url, path)
    _assert(
        response.status == expected_status,
        f"{path} returned HTTP {response.status}, expected {expected_status}: {response.text()[:500]}",
    )
    try:
        payload = response.json()
    except Exception as exc:
        raise AssertionError(f"{path} did not return valid JSON: {response.text()[:500]}") from exc
    _assert(isinstance(payload, dict), f"{path} returned non-object JSON")
    return response, payload


def _poll_exact_deployment(
    base_url: str,
    expected_commit: str,
    *,
    max_wait_seconds: int,
    poll_seconds: int,
) -> dict:
    expected = expected_commit.strip().lower()
    _assert(bool(expected), "expected commit is required")
    deadline = time.monotonic() + max(1, max_wait_seconds)
    attempts = 0
    last_observation: dict[str, Any] = {}

    while True:
        attempts += 1
        dns = _dns_diagnostic(base_url)
        if not dns.get("ok"):
            last_observation = dict(dns)
            print(
                f"[production-smoke] DNS resolution failed before /health "
                f"(attempt {attempts}): {dns.get('error')}",
                flush=True,
            )
        else:
            try:
                response = _request(base_url, "/health", timeout=DEFAULT_REQUEST_TIMEOUT)
                if response.status == 200:
                    payload = response.json()
                    deployment = payload.get("deployment") or {}
                    observed = str(deployment.get("commit") or "").strip().lower()
                    last_observation = {
                        "stage": "health",
                        "httpStatus": response.status,
                        "ok": payload.get("ok"),
                        "status": payload.get("status"),
                        "version": payload.get("version"),
                        "branch": deployment.get("branch"),
                        "commit": observed,
                        "databaseKind": (payload.get("database") or {}).get("kind"),
                        "migrationsOk": (payload.get("migrations") or {}).get("ok"),
                        "configurationOk": (payload.get("configuration") or {}).get("ok"),
                        "dns": dns,
                    }
                    if _commit_matches(observed, expected):
                        return {"attempts": attempts, "payload": payload, "network": dns}
                    print(
                        f"[production-smoke] waiting for Render commit {expected[:12]}; "
                        f"currently {observed or 'unknown'} (attempt {attempts})",
                        flush=True,
                    )
                else:
                    last_observation = {
                        "stage": "http",
                        "httpStatus": response.status,
                        "body": response.text()[:500],
                        "dns": dns,
                    }
                    print(
                        f"[production-smoke] /health HTTP {response.status}; "
                        f"waiting for deployment (attempt {attempts})",
                        flush=True,
                    )
            except (
                URLError,
                TimeoutError,
                OSError,
                http.client.HTTPException,
                ValueError,
                json.JSONDecodeError,
            ) as exc:
                stage = _network_error_stage(exc)
                last_observation = {
                    "stage": stage,
                    "error": f"{type(exc).__name__}: {exc}",
                    "dns": dns,
                }
                print(
                    f"[production-smoke] /health unavailable at stage={stage}: {exc}",
                    flush=True,
                )

        if time.monotonic() >= deadline:
            raise AssertionError(
                f"Render did not converge to commit {expected[:12]} within the acceptance window; "
                f"last observation={last_observation!r}"
            )
        time.sleep(max(1, poll_seconds))

def run(base_url: str, expected_commit: str, *, max_wait_seconds: int, poll_seconds: int) -> dict:
    started_at = time.time()
    result: dict[str, Any] = {
        "baseUrl": base_url.rstrip("/"),
        "expectedCommit": expected_commit.strip().lower()[:12],
        "checks": {},
    }

    with _check_stage("deployment"):
        deployment = _poll_exact_deployment(
            base_url,
            expected_commit,
            max_wait_seconds=max_wait_seconds,
            poll_seconds=poll_seconds,
        )

    with _check_stage("health"):
        health = deployment["payload"]
        result["checks"]["network"] = deployment.get("network") or {}
        health_deployment = health.get("deployment") or {}
        _assert(health.get("ok") is True, "/health ok must be true")
        _assert(health.get("status") == "healthy", "/health status must be healthy")
        _assert(
            health.get("version") == EXPECTED_VERSION,
            f"unexpected production version: {health.get('version')!r}; expected {EXPECTED_VERSION!r}",
        )
        _assert(health_deployment.get("provider") == "render", "production provider must be render")
        _assert(
            health_deployment.get("branch") == "main",
            f"production branch must be main, got {health_deployment.get('branch')!r}",
        )
        _assert((health.get("database") or {}).get("ok") is True, "production database is not healthy")
        _assert(
            (health.get("database") or {}).get("kind") == "postgres",
            "production database must be PostgreSQL/Supabase",
        )
        _assert((health.get("migrations") or {}).get("ok") is True, "production migrations are not healthy")
        _assert((health.get("migrations") or {}).get("missing") == [], "production has missing migrations")
        result["checks"]["health"] = {
            "ok": True,
            "attempts": deployment["attempts"],
            "commit": health_deployment.get("commit"),
            "branch": health_deployment.get("branch"),
            "version": health.get("version"),
            "database": (health.get("database") or {}).get("kind"),
            "migrationCount": len((health.get("migrations") or {}).get("applied") or []),
        }

    with _check_stage("ready"):
        _, ready = _json_endpoint(base_url, "/ready")
        _assert(ready.get("ok") is True and ready.get("status") == "ready", f"/ready is not ready: {ready!r}")
        _assert(
            (ready.get("configuration") or {}).get("ok") is True,
            f"production configuration is not ready: {(ready.get('configuration') or {}).get('warnings')!r}",
        )
        result["checks"]["ready"] = {"ok": True}

    with _check_stage("live"):
        _, live = _json_endpoint(base_url, "/live")
        _assert(live.get("ok") is True and live.get("status") == "live", f"/live is not live: {live!r}")
        result["checks"]["live"] = {"ok": True}

    with _check_stage("homepage"):
        home = _request(base_url, "/")
        _assert(home.status == 200, f"/ returned HTTP {home.status}")
        home_text = home.text()
        _assert("今天的學習，從這裡開始" in home_text, "homepage canonical hero marker is missing")
        _assert("醫學檢驗教學平台" in home_text, "homepage brand marker is missing")
        result["checks"]["homepage"] = {"ok": True}

    with _check_stage("login"):
        login = _request(base_url, "/login")
        _assert(login.status == 200, f"/login returned HTTP {login.status}")
        login_text = login.text()
        _assert('id="login-form"' in login_text, "login form marker is missing")
        _assert("使用者登入" in login_text, "login page title marker is missing")
        result["checks"]["login"] = {"ok": True}

    with _check_stage("anonymousAuth"):
        _, me = _json_endpoint(base_url, "/api/auth/me")
        _assert(me == {"authenticated": False, "user": None}, f"anonymous auth contract drifted: {me!r}")
        result["checks"]["anonymousAuth"] = {"ok": True}

    with _check_stage("anonymousSystemGuard"):
        system = _request(base_url, "/system", follow_redirects=False)
        _assert(
            system.status in {301, 302, 303, 307, 308},
            f"anonymous /system should redirect, got HTTP {system.status}",
        )
        location = system.headers.get("location", "")
        _assert("/login" in location, f"anonymous /system redirect target is unexpected: {location!r}")
        result["checks"]["anonymousSystemGuard"] = {"ok": True, "location": location}

    result["ok"] = True
    result["elapsedSeconds"] = round(time.time() - started_at, 3)
    return result

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--max-wait-seconds", type=int, default=720)
    parser.add_argument("--poll-seconds", type=int, default=15)
    args = parser.parse_args()

    report: dict[str, Any]
    try:
        report = run(
            args.base_url,
            args.expected_commit,
            max_wait_seconds=args.max_wait_seconds,
            poll_seconds=args.poll_seconds,
        )
    except SmokeCheckError as exc:
        report = {
            "ok": False,
            "baseUrl": args.base_url.rstrip("/"),
            "expectedCommit": args.expected_commit.strip().lower()[:12],
            "failedStage": exc.stage,
            "error": f"{type(exc.cause).__name__}: {exc.cause}",
        }
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        return 1
    except Exception as exc:
        report = {
            "ok": False,
            "baseUrl": args.base_url.rstrip("/"),
            "expectedCommit": args.expected_commit.strip().lower()[:12],
            "failedStage": "unknown",
            "error": f"{type(exc).__name__}: {exc}",
        }
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        return 1

    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
