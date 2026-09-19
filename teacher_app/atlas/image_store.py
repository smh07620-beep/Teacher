"""Canonical local Atlas image validation and filesystem storage.

HTTP/RBAC remain in the compatibility adapter. This module owns only safe local
image bytes, filenames, thumbnails and request-path normalization.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import uuid

from PIL import Image


ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
THUMBNAIL_SIZE = (640, 640)


class AtlasImageError(ValueError):
    """Raised when Atlas image bytes or file metadata are not acceptable."""


def image_directory(storage_root) -> Path:
    directory = Path(storage_root) / "atlas_images"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def normalize_extension(filename_or_extension: str) -> str:
    value = str(filename_or_extension or "")
    ext = value.lower() if value.startswith(".") else Path(value).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise AtlasImageError("僅接受 JPG、PNG、WEBP 圖片。")
    return ext


def store_image_bytes(
    storage_root,
    raw: bytes,
    filename_or_extension: str,
    *,
    max_bytes: int | None = MAX_UPLOAD_BYTES,
) -> dict:
    ext = normalize_extension(filename_or_extension)
    if not raw or (max_bytes is not None and len(raw) > max_bytes):
        raise AtlasImageError("圖片不可為空且不得超過 15 MB。")
    try:
        image = Image.open(BytesIO(raw))
        image.verify()
        image = Image.open(BytesIO(raw))
        image.load()
        if image.format not in ALLOWED_FORMATS:
            raise AtlasImageError("圖片內容或 MIME 驗證失敗。")
    except AtlasImageError:
        raise
    except Exception as exc:
        raise AtlasImageError("圖片內容或 MIME 驗證失敗。") from exc

    name = f"{uuid.uuid4().hex}{ext}"
    directory = image_directory(storage_root)
    directory.joinpath(name).write_bytes(raw)
    thumb = image.copy()
    thumb.thumbnail(THUMBNAIL_SIZE)
    thumb.save(directory / f"thumb-{name}", format=image.format)
    return {
        "name": name,
        "imageUrl": f"/api/atlas/images/{name}",
        "thumbnailUrl": f"/api/atlas/images/thumb-{name}",
    }


def requested_image(storage_root, name: str) -> tuple[Path, str, str]:
    safe = Path(str(name or "")).name
    original = safe[6:] if safe.startswith("thumb-") else safe
    if not safe or original != Path(original).name:
        raise AtlasImageError("找不到圖譜圖片。")
    return image_directory(storage_root), safe, f"/api/atlas/images/{original}"
