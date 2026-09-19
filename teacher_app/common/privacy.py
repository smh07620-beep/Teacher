"""Canonical privacy guard for external AI processing."""
from __future__ import annotations

import functools
import os
import re
from pathlib import Path

from flask import jsonify, request


_PATTERNS = [
    (re.compile(r"\b[A-Z][12]\d{8}\b", re.I), "[身分證號已遮罩]"),
    (re.compile(r"\b09\d{8}\b"), "[手機號碼已遮罩]"),
    (re.compile(r"(?i)(病歷號|MRN|病歷編號)\s*[:：#]?\s*[A-Z0-9-]{5,20}"), "病歷號：[已遮罩]"),
    (re.compile(r"(?i)(姓名|病人|患者)\s*[:：]\s*[\u4e00-\u9fffA-Za-z·. ]{2,30}"), r"\1：[已遮罩]"),
    (re.compile(r"(?i)(電話|TEL|PHONE)\s*[:：]?\s*[0-9()+\- ]{7,20}"), r"\1：[已遮罩]"),
    (re.compile(r"(?i)(生日|出生日期|DOB)\s*[:：]?\s*\d{2,4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?"), r"\1：[已遮罩]"),
]

MEDIA_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".mp4", ".webm", ".mov", ".m4v",
    ".mp3", ".wav", ".m4a", ".ogg",
}


def deidentify_text(text: str) -> tuple[str, int]:
    value = str(text or "")
    replacements = 0
    for pattern, replacement in _PATTERNS:
        value, count = pattern.subn(replacement, value)
        replacements += count
    return value, replacements


def deidentification_enabled() -> bool:
    return os.environ.get("AI_DEIDENTIFICATION_ENABLED", "true").strip().lower() not in {
        "0", "false", "no", "off",
    }


def deidentify_external_text(text: object) -> str:
    value = str(text or "")
    if not deidentification_enabled():
        return value
    return deidentify_text(value)[0]


def wrap_text_extractor(namespace, name: str, fn) -> None:
    if getattr(fn, "_teacher64_deid", False):
        return

    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        result = fn(*args, **kwargs)
        if not deidentification_enabled():
            return result
        if isinstance(result, str):
            return deidentify_external_text(result)
        if isinstance(result, tuple) and result and isinstance(result[0], str):
            masked = deidentify_external_text(result[0])
            return (masked, *result[1:])
        return result

    wrapped._teacher64_deid = True
    setattr(namespace, name, wrapped)


def install_extractor_wrappers(namespace, target_names) -> int:
    """Wrap the explicitly declared external-AI text boundaries.

    The canonical AI runtime owns this target list.  Privacy integration must
    fail closed when a declared target is missing instead of silently scanning
    a broad compatibility namespace for implementation markers.
    """

    count = 0
    for name in tuple(target_names or ()):
        fn = getattr(namespace, str(name), None)
        if not callable(fn):
            raise RuntimeError(f"External AI privacy target is unavailable: {name}")
        already_wrapped = bool(getattr(fn, "_teacher64_deid", False))
        wrap_text_extractor(namespace, str(name), fn)
        if not already_wrapped:
            count += 1
    return count


def external_enabled() -> bool:
    return os.environ.get("AI_EXTERNAL_PROCESSING_ENABLED", "true").strip().lower() not in {
        "0", "false", "no", "off",
    }


def external_media_allowed() -> bool:
    return os.environ.get("AI_EXTERNAL_MEDIA_ALLOWED", "false").strip().lower() in {
        "1", "true", "yes", "on",
    }


def register_ai_privacy(app, *, material_lookup):
    if app.extensions.get("teacher_ai_privacy_registered"):
        return app
    from teacher_app.assessments import ai_runtime

    app.extensions["teacher_ai_privacy_registered"] = True
    app.extensions["teacher_ai_deid_wrappers"] = install_extractor_wrappers(
        ai_runtime,
        ai_runtime.EXTERNAL_AI_TEXT_EXTRACTOR_TARGETS,
    )

    @app.before_request
    def teacher_ai_privacy_guard():
        if request.path != "/api/ai-questions/generate" or request.method != "POST":
            return None
        if not external_enabled():
            return jsonify({"error": "院方目前已停用外部 AI 處理。"}), 503
        data = request.get_json(silent=True) or {}
        if isinstance(data.get("focus"), str):
            masked, changed = deidentify_text(data["focus"])
            if changed:
                data["focus"] = masked
                request._cached_json = {False: data, True: data}
        if external_media_allowed():
            return None

        material_ids = data.get("materialIds") if isinstance(data.get("materialIds"), list) else []
        material_ids = list(material_ids)
        one = str(data.get("materialId", "") or "").strip()
        if one and one not in material_ids:
            material_ids.append(one)
        for material_id in material_ids:
            try:
                material = material_lookup(str(material_id))
            except Exception:
                material = None
            if not material:
                continue
            filename = str(
                material.get("filename")
                or material.get("title")
                or material.get("storageFilename")
                or ""
            )
            extension = Path(filename).suffix.lower()
            kind = str(material.get("kind") or material.get("sourceKind") or "").lower()
            if extension in MEDIA_EXT or kind in {"image", "video", "audio"}:
                return jsonify({
                    "error": "6.4 預設禁止將圖片/影音直接送往外部 AI；請改用已去識別的文字教材，或由系統管理者明確開啟 AI_EXTERNAL_MEDIA_ALLOWED。"
                }), 400
        return None

    return app


__all__ = [
    "MEDIA_EXT",
    "deidentification_enabled",
    "deidentify_external_text",
    "deidentify_text",
    "external_enabled",
    "external_media_allowed",
    "install_extractor_wrappers",
    "register_ai_privacy",
    "wrap_text_extractor",
]
