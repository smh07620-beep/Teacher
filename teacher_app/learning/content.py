"""Pure smart-learning content helpers: extraction and completion rules."""
from __future__ import annotations

import re
import zipfile
from pathlib import Path


def extract_slide_text(path: Path):
    """Return reliable native text only; scanned PDFs deliberately return no hits."""
    suffix = path.suffix.lower()
    pages = []
    if suffix == ".pptx":
        with zipfile.ZipFile(path) as archive:
            names = sorted(
                (name for name in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
                key=lambda name: int(re.search(r"\d+", name).group()),
            )
            for number, name in enumerate(names, 1):
                xml = archive.read(name).decode("utf-8", "ignore")
                text = " ".join(re.findall(r"<a:t>(.*?)</a:t>", xml)).strip()
                pages.append((number, text, text.split(" ")[0] if text else ""))
    elif suffix == ".pdf":
        try:
            import fitz
            document = fitz.open(path)
            pages = [
                (index + 1, (page.get_text("text") or "").strip(), "")
                for index, page in enumerate(document)
            ]
            document.close()
        except Exception:
            pages = []
    return [(number, text, title) for number, text, title in pages if text]


def preview_docx_atlas(path: Path):
    """Extract DOCX media references in document order; never publishes."""
    with zipfile.ZipFile(path) as archive:
        document = archive.read("word/document.xml").decode("utf-8", "ignore")
    text = " ".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", document))
    images = []
    for index, relation in enumerate(re.findall(r'(?:embed|link)="rId(\d+)"', document), 1):
        images.append({
            "index": index,
            "relationshipId": "rId" + relation,
            "section": text[:180],
            "caption": "",
            "region": {"x": 0, "y": 0, "width": 1, "height": 1},
        })
    warnings = [] if images else [
        "DOCX 預覽僅處理 inline/table 圖片；浮動圖、群組、SmartArt、圖表與 OLE 保留原文件，需人工處理。"
    ]
    return {"images": images, "warnings": warnings}


def media_completion(duration, watched_buckets, threshold: float = 0.9) -> bool:
    """Server-authoritative ten-second bucket coverage for video/audio."""
    duration = max(0.0, float(duration or 0))
    threshold = max(0.0, min(1.0, float(threshold)))
    if duration <= 0:
        return False
    buckets = {max(0, int(item)) for item in watched_buckets}
    covered = sum(min(10.0, max(0.0, duration - bucket * 10)) for bucket in buckets)
    return covered >= duration * threshold


def resolved_completion(duration, watched_buckets, client_completed, is_media, threshold: float = 0.9) -> bool:
    """Ignore client completion flags for media, retain legacy document flow."""
    return media_completion(duration, watched_buckets, threshold) if is_media else bool(client_completed)
