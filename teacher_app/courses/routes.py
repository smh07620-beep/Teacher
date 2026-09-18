"""Compatibility helpers for course HTTP responses.

Legacy URL rules live in the compatibility host and delegate directly to the
canonical course service.  Runtime view-function replacement has been retired.
"""
from __future__ import annotations

from flask import jsonify

from teacher_app.common.errors import ApiError


def _legacy_error(exc: ApiError):
    body = {"error": exc.message}
    body.update(exc.extra)
    return jsonify(body), exc.status
