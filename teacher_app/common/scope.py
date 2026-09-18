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
    candidate = str(value or "")
    return candidate if candidate in GROUPS else DEFAULT_GROUP


def normalize_area(value: object) -> str:
    candidate = str(value or "")
    return candidate if candidate in TRAINING_AREAS else DEFAULT_TRAINING_AREA
