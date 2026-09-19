"""Canonical built-in material catalog helpers."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
META_FILE = ROOT / "data" / "slides_meta.json"

CATEGORY_LABELS = {
    "subA1": "1-1 一致性與法定傳染病通報",
    "subA2": "1-2 c503一般作業流程與異常訊號故障排除",
    "subA3": "1-3 Cobas b 211異常訊號故障排除與QC設定",
    "zoneB": "2 COVER C1人員考區（Sebia）",
    "": "未分類 / 一般補充教材",
}


def load_builtin_meta() -> list[dict]:
    if not META_FILE.exists():
        return []
    try:
        data = json.loads(META_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return []
    return data if isinstance(data, list) else []
