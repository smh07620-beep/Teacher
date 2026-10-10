"""Atlas cell/structure annotations (teacher-drawn boxes on an Atlas image).

An annotation lives in ``atlas_items.annotation_json``::

    {"version": 1,
     "marks": [{"id": "m1", "label": "嗜中性球", "detail": "...",
                "x": 0.12, "y": 0.30, "w": 0.10, "h": 0.12}]}

Coordinates are fractions (0..1) of the image width/height so they survive
thumbnails, zoom and different screen sizes.  This module is pure (no Flask, no
database): validation for authoring, a learner-safe projection, and the
geometry used to grade a "click the structure" exam question on the server.
"""
from __future__ import annotations

import math
import re
import uuid
from typing import Any, Mapping

from teacher_app.common.errors import ApiError

ANNOTATION_VERSION = 1
MAX_MARKS = 30
MAX_LABEL = 80
MAX_DETAIL = 2000
MIN_SIDE = 0.005  # a box narrower than 0.5% of the image is almost surely a slip
# Forgiveness around a box when grading a click (fraction of image size).
CLICK_TOLERANCE = 0.005
_ID_RE = re.compile(r"[^A-Za-z0-9_-]")


def _bad(message: str) -> ApiError:
    return ApiError("INVALID_ATLAS_ANNOTATION", message, status=400)


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise _bad(f"標記座標 {name} 不正確。")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise _bad(f"標記座標 {name} 不正確。") from None
    if not math.isfinite(number):
        raise _bad(f"標記座標 {name} 不正確。")
    return number


def _mark_id(raw: Any, used: set[str]) -> str:
    cleaned = _ID_RE.sub("", str(raw or "").strip())[:40]
    if not cleaned or cleaned in used:
        cleaned = "m" + uuid.uuid4().hex[:8]
    used.add(cleaned)
    return cleaned


def normalise(value: Any) -> dict:
    """Validate teacher input and return the canonical stored form.

    ``None``/empty/non-dict input means "no annotations" (returns ``{}``).
    Malformed marks raise :class:`ApiError` (400) instead of being silently
    dropped, so a teacher never believes a box was saved when it was not.
    """
    if not isinstance(value, Mapping) or not value:
        return {}
    raw_marks = value.get("marks")
    if raw_marks is None:
        return {}
    if not isinstance(raw_marks, list):
        raise _bad("標記資料格式不正確。")
    if len(raw_marks) > MAX_MARKS:
        raise _bad(f"每張圖譜最多 {MAX_MARKS} 個標記。")
    used: set[str] = set()
    marks: list[dict] = []
    for raw in raw_marks:
        if not isinstance(raw, Mapping):
            raise _bad("標記資料格式不正確。")
        label = str(raw.get("label") or "").strip()[:MAX_LABEL]
        if not label:
            raise _bad("每個標記都要填寫名稱。")
        x, y = _number(raw.get("x"), "x"), _number(raw.get("y"), "y")
        w, h = _number(raw.get("w"), "w"), _number(raw.get("h"), "h")
        if w < MIN_SIDE or h < MIN_SIDE:
            raise _bad(f"標記「{label}」的框太小，請重新框選。")
        if x < 0 or y < 0 or x + w > 1.0001 or y + h > 1.0001:
            raise _bad(f"標記「{label}」超出圖片範圍。")
        marks.append({
            "id": _mark_id(raw.get("id"), used),
            "label": label,
            "detail": str(raw.get("detail") or "").strip()[:MAX_DETAIL],
            "x": round(x, 5), "y": round(y, 5),
            "w": round(min(w, 1.0 - x), 5), "h": round(min(h, 1.0 - y), 5),
        })
    if not marks:
        return {}
    return {"version": ANNOTATION_VERSION, "marks": marks}


def marks_of(annotation: Any) -> list[dict]:
    if not isinstance(annotation, Mapping):
        return []
    marks = annotation.get("marks")
    return [dict(m) for m in marks if isinstance(m, Mapping)] if isinstance(marks, list) else []


def find_mark(annotation: Any, mark_id: str) -> dict | None:
    wanted = str(mark_id or "")
    for mark in marks_of(annotation):
        if str(mark.get("id")) == wanted:
            return mark
    return None


def region_of(mark: Mapping[str, Any]) -> dict:
    """Just the geometry (what the exam snapshot keeps server-side)."""
    return {key: float(mark[key]) for key in ("x", "y", "w", "h")}


def point_in_region(point: Any, region: Any, tolerance: float = CLICK_TOLERANCE) -> bool:
    """Is a learner click ``{"x":..,"y":..}`` inside ``region`` (± tolerance)?"""
    if not isinstance(point, Mapping) or not isinstance(region, Mapping):
        return False
    try:
        px, py = float(point["x"]), float(point["y"])
        x, y = float(region["x"]), float(region["y"])
        w, h = float(region["w"]), float(region["h"])
    except (KeyError, TypeError, ValueError):
        return False
    if not all(math.isfinite(n) for n in (px, py, x, y, w, h)):
        return False
    return (x - tolerance) <= px <= (x + w + tolerance) and (y - tolerance) <= py <= (y + h + tolerance)


def mark_at_point(annotation: Any, point: Any) -> dict | None:
    """Which mark did the learner click?  Smallest box wins when boxes overlap."""
    hits = [
        mark for mark in marks_of(annotation)
        if point_in_region(point, mark, tolerance=0.0)
    ]
    if not hits:
        return None
    return min(hits, key=lambda m: float(m.get("w", 0)) * float(m.get("h", 0)))
