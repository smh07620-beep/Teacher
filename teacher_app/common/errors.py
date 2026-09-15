"""Unified API error types with 6.4-compatible payloads."""

from __future__ import annotations

from typing import Any, Optional

from flask import Flask, jsonify


class ApiError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, extra: Optional[dict] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.extra = extra or {}


def error_body(code: str, message: str, extra: Optional[dict] = None) -> dict[str, Any]:
    """Dual-shape error used during the 6.5 compatibility phase.

    New clients can read ``ok`` + ``errorDetail``. Legacy clients still see
    ``{"error": "<message>"}``.
    """
    payload: dict[str, Any] = {
        "ok": False,
        "error": message,
        "errorDetail": {"code": code, "message": message},
    }
    if extra:
        payload.update(extra)
    return payload


def success_body(data: Optional[dict] = None, extra: Optional[dict] = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": True, "data": data or {}}
    if extra:
        payload.update(extra)
    return payload


def json_error(code: str, message: str, status: int, extra: Optional[dict] = None):
    return jsonify(error_body(code, message, extra)), status


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def handle_api_error(exc: ApiError):
        extra = dict(exc.extra)
        if extra.get("loginRequired"):
            body = error_body(exc.code, exc.message, {"loginRequired": True})
        else:
            body = error_body(exc.code, exc.message, extra or None)
        return jsonify(body), exc.status
