"""Canonical production request-security policy and runtime hooks."""
from __future__ import annotations

import datetime as dt
import os
import threading
import time
from urllib.parse import urlsplit

from flask import g, jsonify, request

from teacher_app.common.auth import has_role


_RATE_LOCK = threading.Lock()
_LOGIN_FAILURES: dict[str, dict] = {}
HOT_PATH_ENDPOINTS = {"api_list_slides", "api_courses"}


def truthy(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def login_rate_limit_status() -> dict:
    """Describe the supported topology of the in-process login limiter."""
    try:
        web_concurrency = max(1, int(os.environ.get("WEB_CONCURRENCY", "1") or 1))
    except (TypeError, ValueError):
        web_concurrency = 1
    return {
        "backend": "process-local",
        "shared": False,
        "webConcurrency": web_concurrency,
        "supportedTopology": "single web process / single service instance",
        "topologySupported": web_concurrency == 1,
    }


def client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    # Render is the trusted edge for production traffic.  Use the right-most
    # forwarded address there so a client-supplied left-most X-Forwarded-For
    # value cannot rotate the login-rate-limit key.  Outside Render, do not
    # trust a forwarding header supplied directly by the caller.
    if forwarded and truthy(os.environ.get("RENDER", "false")):
        parts = [part.strip() for part in forwarded.split(",") if part.strip()]
        if parts:
            return parts[-1][:100]
    return str(request.remote_addr or "unknown")[:100]


def login_key() -> str:
    data = request.get_json(silent=True) or {}
    username = str(data.get("username") or "").strip().lower()[:100]
    return f"{client_ip()}|{username}"


def same_origin(candidate: str) -> bool:
    if not candidate:
        return False
    try:
        parsed = urlsplit(candidate)
        return parsed.netloc.lower() == str(request.host or "").lower()
    except Exception:
        return False


def csrf_origin_ok() -> bool:
    origin = request.headers.get("Origin", "")
    if origin:
        return same_origin(origin)
    referer = request.headers.get("Referer", "")
    if referer:
        return same_origin(referer)
    return False


def register_production_hardening(
    app,
    *,
    current_user,
    login_failures: dict | None = None,
    rate_lock=None,
    clock=time,
):
    if app.extensions.get("production_hardening_registered"):
        return app

    failures_state = _LOGIN_FAILURES if login_failures is None else login_failures
    failures_lock = _RATE_LOCK if rate_lock is None else rate_lock
    require_secret = truthy(os.environ.get("PRODUCTION_REQUIRE_SECRET", "false"))
    configured_secret = os.environ.get("SECRET_KEY", "").strip()
    if require_secret and len(configured_secret) < 32:
        raise RuntimeError("Production requires SECRET_KEY with at least 32 characters.")
    if configured_secret:
        app.config["SECRET_KEY"] = configured_secret

    session_hours = max(1, min(24, int(os.environ.get("SESSION_HOURS", "12") or 12)))
    app.config["PERMANENT_SESSION_LIFETIME"] = dt.timedelta(hours=session_hours)
    if truthy(os.environ.get("SESSION_COOKIE_SECURE", "false")):
        app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    max_attempts = max(3, min(20, int(os.environ.get("LOGIN_RATE_LIMIT_MAX_ATTEMPTS", "5") or 5)))
    window_seconds = max(60, min(3600, int(os.environ.get("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "900") or 900)))
    csrf_origin_check = truthy(os.environ.get("CSRF_ORIGIN_CHECK", "true"))
    csp_enforce = truthy(os.environ.get("CSP_ENFORCE", "false"))
    app.extensions["production_hardening_registered"] = True

    @app.before_request
    def security_preflight():
        if request.endpoint in HOT_PATH_ENDPOINTS:
            g._teacher_material_hot_path_started = clock.perf_counter()
        if request.path == "/api/auth/login" and request.method == "POST":
            key = login_key()
            current_time = clock.time()
            with failures_lock:
                state = failures_state.get(key)
                if state:
                    failures = [
                        timestamp
                        for timestamp in state.get("failures", [])
                        if current_time - timestamp <= window_seconds
                    ]
                    blocked_until = float(state.get("blocked_until", 0) or 0)
                    if blocked_until > current_time:
                        retry = max(1, int(blocked_until - current_time))
                        return jsonify({
                            "error": f"登入失敗次數過多，請 {retry} 秒後再試。",
                            "retryAfter": retry,
                        }), 429, {"Retry-After": str(retry)}
                    failures_state[key] = {"failures": failures, "blocked_until": 0}

        worker_api = request.path.startswith("/api/material-worker/")
        if (
            csrf_origin_check
            and request.path.startswith("/api/")
            and request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and not worker_api
            and not csrf_origin_ok()
        ):
            return jsonify({"error": "安全驗證失敗：請從本站頁面重新操作。"}), 403
        return None

    @app.after_request
    def security_postprocess(response):
        started = getattr(g, "_teacher_material_hot_path_started", None)
        if started is not None and request.endpoint in HOT_PATH_ENDPOINTS:
            duration_ms = (clock.perf_counter() - started) * 1000
            app.logger.info(
                "teacher_stage2 endpoint=%s status=%s duration_ms=%.1f",
                request.endpoint,
                response.status_code,
                duration_ms,
            )
        if request.path == "/api/auth/login" and request.method == "POST":
            key = login_key()
            current_time = clock.time()
            with failures_lock:
                if response.status_code < 400:
                    failures_state.pop(key, None)
                elif response.status_code == 401:
                    state = failures_state.get(key, {"failures": [], "blocked_until": 0})
                    failures = [
                        timestamp
                        for timestamp in state.get("failures", [])
                        if current_time - timestamp <= window_seconds
                    ]
                    failures.append(current_time)
                    blocked_until = 0.0
                    if len(failures) >= max_attempts:
                        exponent = min(5, len(failures) - max_attempts)
                        blocked_until = current_time + min(60, 5 * (2 ** exponent))
                    failures_state[key] = {
                        "failures": failures,
                        "blocked_until": blocked_until,
                    }

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if app.config.get("SESSION_COOKIE_SECURE"):
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        # All live HTML surfaces have converged away from inline scripts and
        # inline event attributes.  Keep the browser-runtime compatibility
        # needed by the current Tailwind/CDN stack, but deny inline script
        # execution globally instead of maintaining a weaker portal branch.
        script_src = (
            "script-src 'self' 'unsafe-eval' https://cdn.tailwindcss.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "script-src-attr 'none'; "
        )
        csp = (
            "default-src 'self'; "
            + script_src
            + "style-src 'self' 'unsafe-inline' https:; "
            "img-src 'self' data: blob: https:; media-src 'self' data: blob: https:; "
            "frame-src 'self' https://www.youtube-nocookie.com https://player.vimeo.com; "
            "connect-src 'self' https:; frame-ancestors 'self'; base-uri 'self'; object-src 'none'"
        )
        response.headers.setdefault(
            "Content-Security-Policy" if csp_enforce else "Content-Security-Policy-Report-Only",
            csp,
        )
        return response

    @app.get("/api/security/status")
    def security_status():
        user = current_user()
        if not user or not any(
            has_role(user, role)
            for role in ("education_admin", "system_admin", "auditor")
        ):
            return jsonify({"error": "權限不足。"}), 403
        return jsonify({
            "sessionHours": session_hours,
            "secureCookie": bool(app.config.get("SESSION_COOKIE_SECURE")),
            "csrfOriginCheck": csrf_origin_check,
            "loginRateLimitMaxAttempts": max_attempts,
            "loginRateLimit": login_rate_limit_status(),
            "cspEnforced": csp_enforce,
            "productionSecretRequired": require_secret,
        })

    return app


__all__ = [
    "HOT_PATH_ENDPOINTS",
    "client_ip",
    "csrf_origin_ok",
    "login_key",
    "login_rate_limit_status",
    "register_production_hardening",
    "same_origin",
    "truthy",
]
