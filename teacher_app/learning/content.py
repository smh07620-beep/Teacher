"""Pure smart-learning content helpers: extraction and completion rules."""
from __future__ import annotations

import re
import zipfile
from pathlib import Path


# File types ``extract_slide_text`` can read.  Cloud-stored originals of any other
# type (video, images, Word...) are never downloaded just to discover they have
# no searchable slide text.
INDEXABLE_SUFFIXES = frozenset({".pptx", ".pdf"})


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



def document_completion(total_pages, visited_pages, threshold: float = 0.9) -> dict:
    """Return server-derived document progress from visited 1-based pages.

    Completion requires both the configured coverage threshold and evidence that
    the learner reached the final page. A direct jump to the last page therefore
    cannot be treated as full completion.
    """
    try:
        total = max(0, int(total_pages or 0))
    except (TypeError, ValueError):
        total = 0
    threshold = max(0.0, min(1.0, float(threshold)))
    if total <= 0:
        return {"completed": False, "progress": 0.0, "visitedPages": []}

    visited = set()
    for value in visited_pages or []:
        try:
            page = int(value)
        except (TypeError, ValueError):
            continue
        if 1 <= page <= total:
            visited.add(page)

    progress = min(100.0, (len(visited) / total) * 100.0)
    completed = total in visited and (progress / 100.0) >= threshold
    return {
        "completed": completed,
        "progress": round(progress, 2),
        "visitedPages": sorted(visited),
    }

def resolved_completion(duration, watched_buckets, client_completed, is_media, threshold: float = 0.9) -> bool:
    """Ignore client completion flags for media, retain legacy document flow."""
    return media_completion(duration, watched_buckets, threshold) if is_media else bool(client_completed)


# ---- Reader rules v2 (minimum dwell per page, anti-skimming) -----------------

def min_dwell_seconds(text_len, override=None) -> int:
    """Minimum seconds a page must stay open: 5s + 5s per 100 characters, max 30s."""
    if override is not None:
        try:
            return max(0, int(override))
        except (TypeError, ValueError):
            pass
    try:
        length = max(0, int(text_len or 0))
    except (TypeError, ValueError):
        length = 0
    return int(min(30, 5 + 5 * (length // 100)))


def clamp_dwell_delta(delta_by_page, elapsed_seconds, slack: float = 5.0) -> dict:
    """Scale a client-reported dwell increment so it cannot exceed real elapsed time."""
    cleaned = {}
    for key, value in (delta_by_page or {}).items():
        try:
            page = int(key)
            seconds = float(value)
        except (TypeError, ValueError):
            continue
        if page >= 1 and seconds > 0:
            cleaned[str(page)] = seconds
    total = sum(cleaned.values())
    allowed = max(0.0, float(elapsed_seconds)) + slack
    if total > allowed and total > 0:
        ratio = allowed / total
        cleaned = {page: seconds * ratio for page, seconds in cleaned.items()}
    return cleaned


def document_completion_v2(total_pages, page_dwell, required_by_page) -> dict:
    """A page counts as read once its accumulated dwell reaches its requirement."""
    try:
        total = max(0, int(total_pages or 0))
    except (TypeError, ValueError):
        total = 0
    if total <= 0:
        return {"completed": False, "progress": 0.0, "readPages": []}
    dwell = page_dwell or {}
    required = required_by_page or {}
    read = []
    for page in range(1, total + 1):
        need = required.get(str(page), required.get(page, 5))
        try:
            have = float(dwell.get(str(page), dwell.get(page, 0)) or 0)
        except (TypeError, ValueError):
            have = 0.0
        if have >= float(need):
            read.append(page)
    progress = round(100.0 * len(read) / total, 2)
    return {"completed": len(read) == total, "progress": progress, "readPages": read}


def limit_new_buckets(new_buckets, known_buckets, elapsed_seconds) -> list:
    """Cap newly credited 10-second buckets to what real elapsed time allows."""
    known = {int(b) for b in known_buckets or []}
    fresh = sorted({int(b) for b in new_buckets or []} - known)
    allowed = int(max(0.0, float(elapsed_seconds)) / 10) + 2
    return sorted(known | set(fresh[:allowed]))
