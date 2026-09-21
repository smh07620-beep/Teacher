"""Canonical training area/group scope definitions.

Keep domain normalization independent from the legacy Flask host so canonical
services do not need an ``app.py`` object merely to validate scope values.
"""
from __future__ import annotations

GROUPS = {
    "grpBio": "1 生化組",
    "grpMicro": "2 鏡檢組",
    "grpSero": "3 血清組",
    "grpBB": "4 血庫組",
    "grpBact": "5 細菌組",
    "grpHema": "6 血液組",
    "grpNew": "新進醫檢師專區",
    "grpPgyDocs": "PGY專用資料放置區",
}
PGY_ONLY_GROUPS = {"grpNew", "grpPgyDocs"}
DEFAULT_GROUP = "grpBio"

TRAINING_AREAS = {
    "internal": "內部教育訓練區",
    "pgy": "PGY訓練區",
}
DEFAULT_TRAINING_AREA = "internal"


def normalize_group(value: object) -> str:
    """Compatibility normalizer for existing/read-side data.

    Historical rows may contain blank or unknown values. Read-side callers keep
    the established fallback to ``DEFAULT_GROUP``. New write paths should call
    :func:`validate_group` so invalid user input cannot silently become grpBio.
    """
    candidate = str(value or "")
    return candidate if candidate in GROUPS else DEFAULT_GROUP


def normalize_area(value: object) -> str:
    """Compatibility normalizer for existing/read-side data.

    New writes should use :func:`validate_area` instead of silently falling back
    to the internal training area.
    """
    candidate = str(value or "")
    return candidate if candidate in TRAINING_AREAS else DEFAULT_TRAINING_AREA


def validate_group(value: object, *, default: str | None = DEFAULT_GROUP) -> str:
    """Return a canonical group for a write or reject invalid input.

    ``default`` is used only when the caller intentionally permits an omitted
    value (for example, create flows that historically defaulted to grpBio).
    Pass ``default=None`` for update fields where blank/unknown input must fail.
    """
    candidate = str(value or "").strip()
    if not candidate:
        if default is None:
            raise ValueError("組別不可空白。")
        candidate = str(default).strip()
    if candidate not in GROUPS:
        raise ValueError("組別格式不正確。")
    return candidate


def validate_area(value: object, *, default: str | None = DEFAULT_TRAINING_AREA) -> str:
    """Return a canonical training area for a write or reject invalid input."""
    candidate = str(value or "").strip()
    if not candidate:
        if default is None:
            raise ValueError("訓練區不可空白。")
        candidate = str(default).strip()
    if candidate not in TRAINING_AREAS:
        raise ValueError("訓練區格式不正確。")
    return candidate


__all__ = [
    "DEFAULT_GROUP",
    "DEFAULT_TRAINING_AREA",
    "GROUPS",
    "PGY_ONLY_GROUPS",
    "TRAINING_AREAS",
    "normalize_area",
    "normalize_group",
    "validate_area",
    "validate_group",
]
