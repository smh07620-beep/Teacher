"""One-pass upload analysis run by the worker while the file is being processed.

Combines the material-type decision and (for Word files) the embedded-image
summary into a single JSON object stored in ``storage_meta['uploadAnalysis']``.
Teachers therefore see the result as soon as *that file* finishes, it survives a
page reload, and nothing has to download the Word file again just to count its
pictures.  Image bytes are never stored here; thumbnails are produced on demand.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

# Methods whose decision rests on a clear signal.  "預設分類" means nothing
# matched, so the teacher should be asked once.
_CONFIDENT_METHODS = {"人工指定", "副檔名判斷", "檔名判斷", "內容規則判斷", "Groq AI 內容判斷"}
IMAGE_SCAN_EXTENSIONS = {".docx"}


def build_analysis(
    path: Path,
    *,
    extension: str,
    resolved_type: str,
    method: str,
    reason: str = "",
) -> dict[str, Any]:
    confident = str(method or "") in _CONFIDENT_METHODS
    analysis: dict[str, Any] = {
        "version": 1,
        "type": str(resolved_type or "standard"),
        "method": str(method or ""),
        "reason": str(reason or "")[:240],
        "confidence": "high" if confident else "low",
        "needsReview": not confident,
        "imageCount": 0,
        "images": [],
    }
    if str(extension or "").lower() in IMAGE_SCAN_EXTENSIONS:
        try:
            from teacher_app.atlas.importer import summarize_docx_images

            summary = summarize_docx_images(Path(path))
            analysis["imageCount"] = int(summary.get("imageCount") or 0)
            analysis["images"] = list(summary.get("images") or [])
            if summary.get("truncated"):
                analysis["imagesTruncated"] = True
            if summary.get("error"):
                analysis["imageScanError"] = str(summary["error"])[:60]
        except Exception as exc:  # analysis must never fail the upload
            LOGGER.warning("upload image scan skipped: %s", type(exc).__name__)
            analysis["imageScanError"] = type(exc).__name__
    return analysis


__all__ = ["build_analysis"]
