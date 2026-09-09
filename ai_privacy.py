"""Teacher 6.4 privacy guard for external AI question generation."""
from __future__ import annotations

import functools
import os
import re
from pathlib import Path

from flask import jsonify, request

# Conservative patterns for common identifiers seen in Taiwanese clinical teaching
# material. They intentionally mask rather than try to infer whether a value is a
# real patient identifier.
_PATTERNS = [
    (re.compile(r"\b[A-Z][12]\d{8}\b", re.I), "[身分證號已遮罩]"),
    (re.compile(r"\b09\d{8}\b"), "[手機號碼已遮罩]"),
    (re.compile(r"(?i)(病歷號|MRN|病歷編號)\s*[:：#]?\s*[A-Z0-9-]{5,20}"), "病歷號：[已遮罩]"),
    (re.compile(r"(?i)(姓名|病人|患者)\s*[:：]\s*[\u4e00-\u9fffA-Za-z·. ]{2,30}"), r"\1：[已遮罩]"),
    (re.compile(r"(?i)(電話|TEL|PHONE)\s*[:：]?\s*[0-9()+\- ]{7,20}"), r"\1：[已遮罩]"),
    (re.compile(r"(?i)(生日|出生日期|DOB)\s*[:：]?\s*\d{2,4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?"), r"\1：[已遮罩]"),
]

MEDIA_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".webm", ".mov", ".m4v", ".mp3", ".wav", ".m4a", ".ogg"}


def deidentify_text(text: str) -> tuple[str, int]:
    value = str(text or "")
    replacements = 0
    for pattern, replacement in _PATTERNS:
        value, n = pattern.subn(replacement, value)
        replacements += n
    return value, replacements


def _code_contains_marker(fn) -> bool:
    code = getattr(fn, "__code__", None)
    if not code:
        return False
    constants = " ".join(str(x) for x in code.co_consts if isinstance(x, str))
    return "教材可擷取的文字太少" in constants or "文字擷取支援" in constants


def _wrap_text_extractor(base, name: str, fn):
    if getattr(fn, "_teacher64_deid", False):
        return

    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        result = fn(*args, **kwargs)
        if os.environ.get("AI_DEIDENTIFICATION_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
            return result
        if isinstance(result, str):
            return deidentify_text(result)[0]
        if isinstance(result, tuple) and result and isinstance(result[0], str):
            masked, _ = deidentify_text(result[0])
            return (masked, *result[1:])
        return result

    wrapped._teacher64_deid = True
    setattr(base, name, wrapped)


def _install_extractor_wrappers(base) -> int:
    count = 0
    for name, fn in list(vars(base).items()):
        if callable(fn) and _code_contains_marker(fn):
            _wrap_text_extractor(base, name, fn)
            count += 1
    return count


def _external_enabled() -> bool:
    return os.environ.get("AI_EXTERNAL_PROCESSING_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}


def _external_media_allowed() -> bool:
    return os.environ.get("AI_EXTERNAL_MEDIA_ALLOWED", "false").strip().lower() in {"1", "true", "yes", "on"}


def register_ai_privacy(base):
    app = base.app
    if app.extensions.get("teacher_ai_privacy_registered"):
        return app
    app.extensions["teacher_ai_privacy_registered"] = True
    app.extensions["teacher_ai_deid_wrappers"] = _install_extractor_wrappers(base)

    @app.before_request
    def teacher_ai_privacy_guard():
        if request.path != "/api/ai-questions/generate" or request.method != "POST":
            return None
        if not _external_enabled():
            return jsonify({"error": "院方目前已停用外部 AI 處理。"}), 503
        data = request.get_json(silent=True) or {}
        # Focus notes are entered directly in the browser and are therefore masked
        # before downstream code can use them as prompt context.
        if isinstance(data.get("focus"), str):
            masked, changed = deidentify_text(data["focus"])
            if changed:
                data["focus"] = masked
                request._cached_json = {False: data, True: data}
        if _external_media_allowed():
            return None
        ids = data.get("materialIds") if isinstance(data.get("materialIds"), list) else []
        one = str(data.get("materialId", "") or "").strip()
        if one and one not in ids:
            ids.append(one)
        for material_id in ids:
            try:
                mat = base.get_material(str(material_id))
            except Exception:
                mat = None
            if not mat:
                continue
            filename = str(mat.get("filename") or mat.get("title") or mat.get("storageFilename") or "")
            ext = Path(filename).suffix.lower()
            kind = str(mat.get("kind") or mat.get("sourceKind") or "").lower()
            if ext in MEDIA_EXT or kind in {"image", "video", "audio"}:
                return jsonify({"error": "6.4 預設禁止將圖片/影音直接送往外部 AI；請改用已去識別的文字教材，或由系統管理者明確開啟 AI_EXTERNAL_MEDIA_ALLOWED。"}), 400
        return None

    return app
