"""JSON success helpers that preserve extra legacy keys when needed."""

from __future__ import annotations

from typing import Any, Optional

from flask import jsonify


def json_ok(data: Optional[dict] = None, extra: Optional[dict] = None, status: int = 200):
    payload: dict[str, Any] = {"ok": True, "data": data or {}}
    if extra:
        payload.update(extra)
    return jsonify(payload), status
