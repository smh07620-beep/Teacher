"""Optional, privacy-first server error reporting (Sentry).

Disabled unless ``SENTRY_DSN`` is set, so a missing DSN (local runs, CI, the
hospital Workers) changes nothing and never imports the SDK.

What leaves the server when enabled: the exception type, message, stack trace,
release/commit and the request *path* of unhandled server errors (HTTP 500).

What never leaves: cookies, request/response headers, request bodies, query
strings, the signed-in user, local variables, breadcrumbs and IP addresses.
Teaching content, exam answers, assessments and account data therefore stay on
the hospital's own infrastructure.  Exception *messages* are still sent, which
is why the application logging policy (docs/ERROR_OBSERVABILITY_CLOSEOUT.md)
forbids personal data and credentials in them.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Mapping
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

_REQUEST_KEYS_TO_DROP = ("cookies", "headers", "data", "query_string", "env", "inferred_content_type")


def scrub_event(event: dict[str, Any], _hint: Any = None) -> dict[str, Any]:
    """Remove everything that could identify a person or carry content."""
    request = event.get("request")
    if isinstance(request, dict):
        for key in _REQUEST_KEYS_TO_DROP:
            request.pop(key, None)
        url = request.get("url")
        if isinstance(url, str) and url:
            parts = urlsplit(url)
            # Keep scheme/host/path only; query strings and fragments can hold tokens.
            request["url"] = f"{parts.scheme}://{parts.netloc}{parts.path}" if parts.netloc else parts.path
    event.pop("user", None)
    event.pop("breadcrumbs", None)
    event.pop("server_name", None)
    return event


def _sample_rate(raw: str) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 1.0
    return min(1.0, max(0.0, value))


def init_error_reporting(
    environ: Mapping[str, str] | None = None,
    *,
    transport: Any = None,
) -> bool:
    """Initialise Sentry when configured.  Returns True only when it is active."""
    env = os.environ if environ is None else environ
    dsn = str(env.get("SENTRY_DSN") or "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
    except ImportError:
        logger.warning("sentry_disabled reason=sdk_not_installed")
        return False

    from teacher_app.maintenance.health import app_version, deployment_identity

    commit = deployment_identity().get("commit")
    release = f"teacher@{app_version()}" + (f"+{commit}" if commit else "")
    options: dict[str, Any] = {
        "dsn": dsn,
        "release": release,
        "environment": str(env.get("SENTRY_ENVIRONMENT") or "production").strip() or "production",
        "integrations": [FlaskIntegration()],
        "send_default_pii": False,
        "max_request_body_size": "never",
        "include_local_variables": False,
        "max_breadcrumbs": 0,
        "traces_sample_rate": 0.0,
        "sample_rate": _sample_rate(str(env.get("SENTRY_SAMPLE_RATE") or "1.0")),
        "before_send": scrub_event,
    }
    if transport is not None:
        options["transport"] = transport
    try:
        sentry_sdk.init(**options)
    except Exception as exc:  # reporting must never stop the site from starting
        logger.warning("sentry_disabled reason=init_failed error_type=%s", type(exc).__name__)
        return False
    # 專案沒有設定記錄等級，INFO 在 Render 記錄裡看不到；用 WARNING 才能讓管理者確認「有啟用」。
    logger.warning("sentry_enabled release=%s", release)
    return True


__all__ = ["init_error_reporting", "scrub_event"]
