"""Post-upload checks the worker runs before learners see a material (2026-10-17).

Findings are stored in ``storageMeta.qualityCheck`` and shown to teachers only.
They never block publishing: a slide that is meant to be a picture or a video
without narration is fine, so every finding is a "please confirm" note.

Runs on the material worker (the teacher's machine / worker host), so it adds no
Render CPU and no Supabase traffic beyond the metadata it already writes.
"""
from __future__ import annotations

import datetime as dt
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
BLANK_STDDEV = 2.5          # grey-level spread below this looks like one flat colour
SILENT_MAX_DB = -50.0       # loudest moment quieter than this is effectively silence
SHORT_MEDIA_SECONDS = 3.0
LOUDNESS_SAMPLE_SECONDS = 600


def _page_number(path: Path) -> int:
    match = re.search(r"(\d+)", path.stem)
    return int(match.group(1)) if match else 0


def page_images(slides_dir: Path) -> list[Path]:
    """One image per page (the reader's 1280px copies are skipped)."""
    if not slides_dir or not Path(slides_dir).is_dir():
        return []
    files = [p for p in Path(slides_dir).iterdir() if p.suffix.lower() in IMAGE_SUFFIXES and "1280" not in p.stem and "thumb" not in p.stem]
    return sorted(files, key=_page_number)


def blank_pages(images: Iterable[Path]) -> list[int]:
    from PIL import Image, ImageStat

    found = []
    for index, path in enumerate(images, start=1):
        try:
            with Image.open(path) as image:
                small = image.convert("L")
                small.thumbnail((160, 160))
                if ImageStat.Stat(small).stddev[0] < BLANK_STDDEV:
                    found.append(_page_number(path) or index)
        except Exception:
            continue  # unreadable page is reported by the renderer, not here
    return found


def max_volume_db(ffmpeg: str, media: Path, *, timeout: int = 180) -> float | None:
    """Loudest moment in the first 10 minutes, in dB (None if it cannot be measured)."""
    try:
        completed = subprocess.run(
            [ffmpeg, "-hide_banner", "-nostats", "-t", str(LOUDNESS_SAMPLE_SECONDS), "-i", str(media),
             "-vn", "-af", "volumedetect", "-f", "null", "-"],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except Exception:
        return None
    match = re.search(r"max_volume:\s*(-?[\d.]+|-inf)\s*dB", completed.stderr or "")
    if not match:
        return None
    return -120.0 if match.group(1) == "-inf" else float(match.group(1))


def build(*, page_count: int = 0, blank: list[int] | None = None, media_kind: str = "",
          has_audio: bool | None = None, max_db: float | None = None, duration: float | None = None) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    blank = sorted(set(blank or []))
    if blank:
        shown = "、".join(str(n) for n in blank[:10]) + ("…" if len(blank) > 10 else "")
        issues.append({"code": "blank_pages", "label": f"{len(blank)} 頁看起來是空白", "detail": f"第 {shown} 頁幾乎沒有內容，請確認是否多放了空白頁。", "pages": blank})
    if media_kind in {"video", "audio"}:
        if duration is not None and 0 < duration < SHORT_MEDIA_SECONDS:
            issues.append({"code": "very_short", "label": "影音很短", "detail": f"只有 {duration:.1f} 秒，請確認是否上傳到正確的檔案。"})
        if media_kind == "video" and has_audio is False:
            issues.append({"code": "no_audio_track", "label": "影片沒有聲音軌", "detail": "這部影片沒有聲音；如果原本應該有講解，請重新匯出後再上傳。"})
        elif max_db is not None and max_db <= SILENT_MAX_DB:
            issues.append({"code": "silent_audio", "label": "幾乎聽不到聲音", "detail": "聲音非常小或完全無聲，請確認錄音時麥克風是否有開。"})
    if page_count == 0 and media_kind not in {"video", "audio"} and not blank:
        issues.append({"code": "no_pages", "label": "沒有產生任何頁面", "detail": "轉檔後沒有頁面，學員會看到空白；請重新上傳或換成 PDF。"})
    return {"checkedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "issues": issues}
