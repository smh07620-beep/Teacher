"""Detect why an Office -> PDF conversion may not match the original layout.

LibreOffice renders PowerPoint/Word files with its own text engine. Two causes
account for most "text overlaps after upload" reports:

* a font used by the deck is not installed on the conversion machine, so a
  substitute with different metrics is used; and
* a text box uses PowerPoint's "shrink text on overflow" (``normAutofit``),
  which LibreOffice re-computes differently.

This module only *reports* these risks. It never changes the conversion, never
raises into the worker (a failed check returns no warnings), and reads the
source file read-only.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Iterable

# Theme placeholders such as "+mn-lt" resolve through the theme, not by name.
_THEME_PLACEHOLDER = re.compile(r"^\+m[jn]-(lt|ea|cs)$")
_TYPEFACE = re.compile(r'<a:(?:latin|ea|cs)\b[^>]*\btypeface="([^"]*)"')
_WORD_FONT = re.compile(r'<w:rFonts\b([^>]*)/?>')
_WORD_FONT_ATTR = re.compile(r'w:(?:ascii|hAnsi|eastAsia|cs)="([^"]*)"')
_NORM_AUTOFIT = re.compile(r"<a:normAutofit\b([^>]*)/?>")
_FONT_SCALE = re.compile(r'fontScale="(\d+)"')

# Families that every conversion host resolves to a metric-compatible face, or
# that are generic keywords rather than real families.
_ALWAYS_OK = {
    "", "serif", "sans-serif", "monospace", "symbol", "wingdings", "wingdings 2",
    "wingdings 3", "webdings", "arial", "times new roman", "courier new",
}

_MAX_XML_BYTES = 8 * 1024 * 1024


def _read_parts(path: Path, prefixes: Iterable[str]) -> Iterable[tuple[str, str]]:
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            name = info.filename
            if not name.endswith(".xml") or not name.startswith(tuple(prefixes)):
                continue
            if info.file_size > _MAX_XML_BYTES:
                continue
            yield name, archive.read(info).decode("utf-8", errors="ignore")


def fonts_used(path: Path) -> set[str]:
    """Return the font family names an OOXML file refers to by name."""
    path = Path(path)
    suffix = path.suffix.lower()
    found: set[str] = set()
    try:
        if suffix in {".pptx", ".ppsx", ".potx"}:
            for _name, xml in _read_parts(path, ("ppt/slides/", "ppt/slideLayouts/", "ppt/slideMasters/", "ppt/theme/")):
                found.update(_TYPEFACE.findall(xml))
        elif suffix in {".docx", ".dotx"}:
            for _name, xml in _read_parts(path, ("word/document", "word/styles", "word/theme/")):
                found.update(_TYPEFACE.findall(xml))
                for attrs in _WORD_FONT.findall(xml):
                    found.update(_WORD_FONT_ATTR.findall(attrs))
    except (zipfile.BadZipFile, OSError, KeyError):
        return set()
    return {name.strip() for name in found if name.strip() and not _THEME_PLACEHOLDER.match(name.strip())}


def autofit_slide_count(path: Path) -> int:
    """Slides containing text that PowerPoint has already auto-shrunk."""
    path = Path(path)
    if path.suffix.lower() not in {".pptx", ".ppsx", ".potx"}:
        return 0
    count = 0
    try:
        for _name, xml in _read_parts(path, ("ppt/slides/slide",)):
            for attrs in _NORM_AUTOFIT.findall(xml):
                match = _FONT_SCALE.search(attrs)
                # fontScale is in 1/1000 percent; 100000 means "not shrunk".
                if match and int(match.group(1)) < 100000:
                    count += 1
                    break
    except (zipfile.BadZipFile, OSError):
        return 0
    return count


def installed_fonts() -> set[str]:
    """Lower-cased family names installed on this conversion host."""
    families: set[str] = set()
    if sys.platform.startswith("win"):
        try:
            import winreg  # type: ignore[import-not-found]

            for hive, sub in (
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
            ):
                try:
                    with winreg.OpenKey(hive, sub) as key:
                        index = 0
                        while True:
                            try:
                                name, _value, _kind = winreg.EnumValue(key, index)
                            except OSError:
                                break
                            index += 1
                            # "Microsoft JhengHei & Microsoft JhengHei UI (TrueType)"
                            base = re.sub(r"\s*\((?:TrueType|OpenType|All res)\)\s*$", "", name)
                            families.update(part.strip().lower() for part in base.split("&") if part.strip())
                except OSError:
                    continue
        except ImportError:
            pass
        return families
    tool = shutil.which("fc-list")
    if not tool:
        return families
    try:
        out = subprocess.run([tool, ":", "family"], capture_output=True, text=True, timeout=20, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return families
    for line in out.splitlines():
        for name in line.split(","):
            if name.strip():
                families.add(name.strip().lower())
    return families


def missing_fonts(used: Iterable[str], installed: set[str]) -> list[str]:
    if not installed:
        # Could not enumerate fonts on this host: say nothing rather than guess.
        return []
    result = []
    for name in sorted({value.strip() for value in used}):
        lowered = name.lower()
        if lowered in _ALWAYS_OK or lowered in installed:
            continue
        result.append(name)
    return result


def conversion_warnings(source: Path, *, installed: set[str] | None = None) -> list[dict]:
    """Return JSON-safe warnings to store on the material; never raises."""
    warnings: list[dict] = []
    try:
        source = Path(source)
        used = fonts_used(source)
        missing = missing_fonts(used, installed_fonts() if installed is None else installed)
        if missing:
            shown = missing[:6]
            warnings.append({
                "code": "missing_fonts",
                "fonts": [name[:80] for name in missing[:20]],
                "message": "轉檔主機缺少字型：" + "、".join(shown) + ("…" if len(missing) > 6 else "")
                + "。已改用替代字型，文字可能位移或重疊。",
            })
        shrunk = autofit_slide_count(source)
        if shrunk:
            warnings.append({
                "code": "autofit_text",
                "slides": shrunk,
                "message": f"有 {shrunk} 張投影片使用「自動縮小文字」，轉檔後行距可能與原檔不同。",
            })
        if warnings:
            warnings.append({
                "code": "suggest_pdf",
                "message": "若轉檔結果與原檔不同，建議在 PowerPoint／Word 選「另存新檔 → PDF」後改傳 PDF，版面會與原檔一致。",
            })
    except Exception:  # noqa: BLE001 - a diagnostic must never fail a material job
        return []
    return warnings


__all__ = ["conversion_warnings", "fonts_used", "autofit_slide_count", "installed_fonts", "missing_fonts"]
