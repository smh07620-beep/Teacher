"""Production security hardening for Teacher 6.3."""
from __future__ import annotations

import datetime as _dt
import os
import threading
import time
from urllib.parse import urlsplit

from flask import jsonify, request


_RATE_LOCK = threading.Lock()
_LOGIN_FAILURES = {}


def _truthy(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()[:100]
    return str(request.remote_addr or "unknown")[:100]


def _login_key() -> str:
    data = request.get_json(silent=True) or {}
    username = str(data.get("username") or "").strip().lower()[:100]
    return f"{_client_ip()}|{username}"


def _same_origin(candidate: str) -> bool:
    if not candidate:
        return False
    try:
        parsed = urlsplit(candidate)
        return parsed.netloc.lower() == str(request.host or "").lower()
    except Exception:
        return False


def _csrf_origin_ok() -> bool:
    origin = request.headers.get("Origin", "")
    if origin:
        return _same_origin(origin)
    referer = request.headers.get("Referer", "")
    if referer:
        return _same_origin(referer)
    return False


def register_production_hardening(base):
    app = base.app
    if app.extensions.get("production_hardening_registered"):
        return app

    require_secret = _truthy(os.environ.get("PRODUCTION_REQUIRE_SECRET", "false"))
    configured_secret = os.environ.get("SECRET_KEY", "").strip()
    if require_secret and len(configured_secret) < 32:
        raise RuntimeError("Production requires SECRET_KEY with at least 32 characters.")
    if configured_secret:
        app.config["SECRET_KEY"] = configured_secret

    session_hours = max(1, min(24, int(os.environ.get("SESSION_HOURS", "12") or 12)))
    app.config["PERMANENT_SESSION_LIFETIME"] = _dt.timedelta(hours=session_hours)
    if _truthy(os.environ.get("SESSION_COOKIE_SECURE", "false")):
        app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    max_attempts = max(3, min(20, int(os.environ.get("LOGIN_RATE_LIMIT_MAX_ATTEMPTS", "5") or 5)))
    window_seconds = max(60, min(3600, int(os.environ.get("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "900") or 900)))
    csrf_origin_check = _truthy(os.environ.get("CSRF_ORIGIN_CHECK", "true"))
    csp_enforce = _truthy(os.environ.get("CSP_ENFORCE", "false"))
    app.extensions["production_hardening_registered"] = True

    @app.before_request
    def security_preflight():
        if request.path == "/api/auth/login" and request.method == "POST":
            key = _login_key()
            now = time.time()
            with _RATE_LOCK:
                state = _LOGIN_FAILURES.get(key)
                if state:
                    failures = [ts for ts in state.get("failures", []) if now - ts <= window_seconds]
                    blocked_until = float(state.get("blocked_until", 0) or 0)
                    if blocked_until > now:
                        retry = max(1, int(blocked_until - now))
                        return jsonify({"error": f"登入失敗次數過多，請 {retry} 秒後再試。", "retryAfter": retry}), 429, {"Retry-After": str(retry)}
                    _LOGIN_FAILURES[key] = {"failures": failures, "blocked_until": 0}
        if csrf_origin_check and request.path.startswith("/api/") and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if not _csrf_origin_ok():
                return jsonify({"error": "安全驗證失敗：請從本站頁面重新操作。"}), 403
        return None

    @app.after_request
    def security_postprocess(response):
        if request.path == "/api/auth/login" and request.method == "POST":
            key = _login_key()
            now = time.time()
            with _RATE_LOCK:
                if response.status_code < 400:
                    _LOGIN_FAILURES.pop(key, None)
                elif response.status_code == 401:
                    state = _LOGIN_FAILURES.get(key, {"failures": [], "blocked_until": 0})
                    failures = [ts for ts in state.get("failures", []) if now - ts <= window_seconds]
                    failures.append(now)
                    blocked_until = 0.0
                    if len(failures) >= max_attempts:
                        exponent = min(5, len(failures) - max_attempts)
                        blocked_until = now + min(60, 5 * (2 ** exponent))
                    _LOGIN_FAILURES[key] = {"failures": failures, "blocked_until": blocked_until}

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if app.config.get("SESSION_COOKIE_SECURE"):
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https:; "
            "img-src 'self' data: blob: https:; media-src 'self' data: blob: https:; "
            "connect-src 'self' https:; frame-ancestors 'self'; base-uri 'self'; object-src 'none'"
        )
        response.headers.setdefault("Content-Security-Policy" if csp_enforce else "Content-Security-Policy-Report-Only", csp)
        return response

    @app.get("/api/security/status")
    def security_status():
        user = base._current_user()
        if not user or base.normalize_role(user.get("role")) not in {"education_admin", "system_admin", "auditor"}:
            return jsonify({"error": "權限不足。"}), 403
        return jsonify({
            "sessionHours": session_hours,
            "secureCookie": bool(app.config.get("SESSION_COOKIE_SECURE")),
            "csrfOriginCheck": csrf_origin_check,
            "loginRateLimitMaxAttempts": max_attempts,
            "cspEnforced": csp_enforce,
            "productionSecretRequired": require_secret,
        })

    return app
