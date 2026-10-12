"""One-pass upload analysis run by the worker while the file is being processed.

Combines the material-type decision and (for Word files) the embedded-image
summary into a single JSON object stored in ``storage_meta['uploadAnalysis']``.
Teachers therefore see the result as soon as *that file* finishes, it survives a
page reload, and nothing has to download the Word file again just to count its
pictures.  Image bytes are never stored here; thumbnails are produced on demand.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

# Methods whose decision rests on a clear signal.  "預設分類" means nothing
# matched, so the teacher should be asked once.
_CONFIDENT_METHODS = {"人工指定", "副檔名判斷", "檔名判斷", "內容規則判斷", "Groq AI 內容判斷"}
IMAGE_SCAN_EXTENSIONS = {".docx"}
# Legacy Word 97-2003 files are converted to a throw-away .docx just to count
# pictures; the stored original is never touched.
LEGACY_WORD_EXTENSIONS = {".doc"}
LEGACY_CONVERT_TIMEOUT_SECONDS = 90


def _convert_doc_to_docx(path: Path, out_dir: Path) -> Path:
    """Convert a legacy .doc to .docx with headless LibreOffice (temp copy only)."""
    binary = os.environ.get("SOFFICE_PATH") or shutil.which("soffice") or shutil.which("libreoffice")
    if not binary:
        raise FileNotFoundError("soffice")
    source = out_dir / "source.doc"
    shutil.copyfile(path, source)
    profile = out_dir / "profile"
    subprocess.run(
        [
            binary,
            f"-env:UserInstallation=file://{profile.as_posix()}",
            "--headless", "--norestore", "--convert-to", "docx:MS Word 2007 XML",
            "--outdir", str(out_dir), str(source),
        ],
        check=True,
        capture_output=True,
        timeout=LEGACY_CONVERT_TIMEOUT_SECONDS,
    )
    converted = out_dir / "source.docx"
    if not converted.is_file():
        raise RuntimeError("convert-no-output")
    return converted


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
    ext = str(extension or "").lower()
    if ext in IMAGE_SCAN_EXTENSIONS or ext in LEGACY_WORD_EXTENSIONS:
        try:
            from teacher_app.atlas.importer import summarize_docx_images

            if ext in LEGACY_WORD_EXTENSIONS:
                analysis["imageScanSource"] = "doc-converted"
                with tempfile.TemporaryDirectory(prefix="doc-scan-") as tmp:
                    summary = summarize_docx_images(_convert_doc_to_docx(Path(path), Path(tmp)))
            else:
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
