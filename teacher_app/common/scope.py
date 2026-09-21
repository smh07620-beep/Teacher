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
    """Project legacy/stored group data to a safe known value.

    This compatibility helper intentionally preserves the historical fallback
    used while reading old rows.  New writes must use :func:`validate_group`
    so malformed input is rejected instead of silently becoming ``grpBio``.
    """

    candidate = str(value or "")
    return candidate if candidate in GROUPS else DEFAULT_GROUP


def normalize_area(value: object) -> str:
    """Project legacy/stored training-area data to a safe known value.

    New writes must use :func:`validate_area`; this fallback remains only for
    reading/projection compatibility with historical rows.
    """

    candidate = str(value or "")
    return candidate if candidate in TRAINING_AREAS else DEFAULT_TRAINING_AREA


def validate_group(value: object) -> str:
    """Return a canonical group for a write or raise ``ValueError``.

    Missing values should be defaulted by the caller before validation.  A
    non-empty unknown value is never rewritten to another group's scope.
    """

    candidate = str(value or "").strip()
    if candidate not in GROUPS:
        raise ValueError("組別格式不正確。")
    return candidate


def validate_area(value: object) -> str:
    """Return a canonical training area for a write or raise ``ValueError``."""

    candidate = str(value or "").strip()
    if candidate not in TRAINING_AREAS:
        raise ValueError("訓練區格式不正確。")
    return candidate
