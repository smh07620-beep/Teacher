"""Minimal cookie-session HTTP client for the production monitoring scripts.

Shared by ``production_worker_check.py`` (authenticated, read-only Worker status)
and ``production_synthetic.py`` (end-to-end synthetic transaction).  Standard
library only so it runs on a bare GitHub runner.  Credentials are never printed.

``tools/production_smoke.py`` stays strictly anonymous/read-only (its acceptance
test forbids mutating verbs); everything that needs a login lives here.
"""
from __future__ import annotations

import json
import time
from http.cookiejar import CookieJar
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener

USER_AGENT = "TeacherProductionMonitor/1.0"
RETRYABLE = {502, 503, 504}


class ApiError(RuntimeError):
    def __init__(self, message: str, *, status: int = 0, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


class ProductionClient:
    def __init__(self, base_url: str, *, timeout: float = 30.0, attempts: int = 3, retry_delay: float = 3.0) -> None:
        self.base_url = str(base_url or "").rstrip("/")
        if not self.base_url.startswith("https://") and "127.0.0.1" not in self.base_url and "localhost" not in self.base_url:
            raise ApiError("base URL 必須是 https://")
        self.timeout = timeout
        self.attempts = max(1, attempts)
        self.retry_delay = retry_delay
        self._opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def request(
        self,
        method: str,
        path_or_url: str,
        *,
        json_body: Any = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        send_cookies: bool = True,
    ) -> tuple[int, dict[str, str], bytes]:
        """Return ``(status, headers, body)``; HTTP error statuses are returned, not raised."""
        url = path_or_url if path_or_url.startswith("http") else urljoin(self.base_url + "/", path_or_url.lstrip("/"))
        merged = {"Accept": "application/json,*/*;q=0.8", "User-Agent": USER_AGENT, "Cache-Control": "no-cache"}
        body = data
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            merged["Content-Type"] = "application/json"
        merged.update(headers or {})
        opener = self._opener if send_cookies else build_opener()
        retry_ok = method.upper() == "GET"
        last_error: Exception | None = None
        for attempt in range(1, self.attempts + 1):
            request = Request(url, data=body, headers=merged, method=method.upper())
            try:
                with opener.open(request, timeout=timeout or self.timeout) as response:
                    status, resp_headers, payload = int(response.getcode() or 0), dict(response.headers.items()), response.read()
            except HTTPError as exc:
                status, resp_headers = int(exc.code or 0), dict(exc.headers.items()) if exc.headers else {}
                try:
                    payload = exc.read()
                except Exception:
                    payload = b""
            except (URLError, TimeoutError, OSError) as exc:
                last_error = exc
                if retry_ok and attempt < self.attempts:
                    time.sleep(self.retry_delay)
                    continue
                raise ApiError(f"{method} {path_or_url} 連線失敗：{type(exc).__name__}") from exc
            if status in RETRYABLE and retry_ok and attempt < self.attempts:
                time.sleep(self.retry_delay)
                continue
            return status, {k.lower(): v for k, v in resp_headers.items()}, payload
        raise ApiError(f"{method} {path_or_url} 失敗：{type(last_error).__name__ if last_error else 'unknown'}")

    def json(self, method: str, path: str, *, json_body: Any = None, expected: tuple[int, ...] = (200,)) -> dict[str, Any]:
        status, _headers, payload = self.request(method, path, json_body=json_body)
        text = payload.decode("utf-8", errors="replace")
        if status not in expected:
            raise ApiError(f"{method} {path} 回傳 HTTP {status}：{text[:300]}", status=status, body=text[:2000])
        try:
            parsed = json.loads(text) if text.strip() else {}
        except ValueError as exc:
            raise ApiError(f"{method} {path} 不是有效的 JSON：{text[:200]}", status=status, body=text[:2000]) from exc
        if isinstance(parsed, list):
            return {"items": parsed}
        return parsed if isinstance(parsed, dict) else {}

    def login(self, username: str, password: str) -> dict[str, Any]:
        """Sign in with the dedicated monitoring account (never logged)."""
        try:
            data = self.json("POST", "/api/auth/login", json_body={"username": username, "password": password})
        except ApiError as exc:
            if exc.status in {401, 403}:
                raise ApiError("監控帳號登入失敗：帳號或密碼不正確（請更新 GitHub secrets）。", status=exc.status) from None
            raise
        if not data.get("ok"):
            raise ApiError("監控帳號登入失敗。")
        return data.get("user") or {}


__all__ = ["ApiError", "ProductionClient"]
