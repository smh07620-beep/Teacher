"""Compatibility helpers for material HTTP responses.

The production compatibility host keeps the legacy URL rules and delegates
straight to teacher_app.materials.service.  This module no longer replaces live
Flask view functions at runtime.
"""
from __future__ import annotations

from flask import jsonify

from teacher_app.common.errors import ApiError
from teacher_app.materials import bp


def _legacy_error(exc: ApiError):
    body = {"error": exc.message}
    body.update(exc.extra)
    return jsonify(body), exc.status
