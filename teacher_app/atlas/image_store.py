"""Canonical local Atlas image validation and filesystem storage.

HTTP/RBAC remain in the compatibility adapter. This module owns only safe local
image bytes, filenames, thumbnails and request-path normalization.
"""
from __future__ import annotations

from io import BytesIO
import logging
import mimetypes
from pathlib import Path
import uuid

from PIL import Image


ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
THUMBNAIL_SIZE = (640, 640)


LOGGER = logging.getLogger(__name__)
# The web host's disk is wiped on every deploy/restart (Render free), so every
# image is also kept in the object store and served from there when the local
# copy is gone.
OBJECT_PREFIX = "atlas-images/"
OBJECT_URL_SECONDS = 3600


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
    mirror_to_object_store(directory, (name, f"thumb-{name}"))
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


def _object_store():
    """(client, bucket) when R2 is configured, else None."""
    try:
        from teacher_app.storage import providers

        if not providers.r2_is_configured():
            return None
        return providers.r2_client(), providers.R2_BUCKET_NAME
    except Exception:
        LOGGER.exception("atlas image object store unavailable")
        return None


def mirror_to_object_store(directory: Path, names) -> bool:
    """Best-effort copy of stored image files to R2 so a redeploy cannot lose them."""
    store = _object_store()
    if store is None:
        return False
    client, bucket = store
    ok = True
    for name in names:
        try:
            path = Path(directory) / name
            client.put_object(
                Bucket=bucket,
                Key=OBJECT_PREFIX + name,
                Body=path.read_bytes(),
                ContentType=mimetypes.guess_type(name)[0] or "application/octet-stream",
                CacheControl="private, max-age=86400",
            )
        except Exception:
            ok = False
            LOGGER.exception("atlas image mirror to object store failed name=%s", name)
    return ok


def object_store_url(name: str) -> str:
    """Short-lived signed URL for an image whose local file is gone, or ''."""
    safe = Path(str(name or "")).name
    store = _object_store()
    if store is None or not safe:
        return ""
    client, bucket = store
    key = OBJECT_PREFIX + safe
    try:
        client.head_object(Bucket=bucket, Key=key)
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=OBJECT_URL_SECONDS,
        )
    except Exception:
        return ""


def delete_image_files(storage_root, image_url: str) -> None:
    """Best-effort removal of an Atlas image, its thumbnail, and their R2 copies."""
    name = Path(str(image_url or "")).name
    if not name or not str(image_url).startswith("/api/atlas/images/") or name.startswith("thumb-"):
        return
    names = (name, f"thumb-{name}")
    try:
        directory = image_directory(storage_root)
        for entry in names:
            try:
                (directory / entry).unlink(missing_ok=True)
            except OSError:
                LOGGER.exception("atlas image local delete failed name=%s", entry)
    except Exception:
        LOGGER.exception("atlas image directory unavailable")
    store = _object_store()
    if store is None:
        return
    client, bucket = store
    for entry in names:
        try:
            client.delete_object(Bucket=bucket, Key=OBJECT_PREFIX + entry)
        except Exception:
            LOGGER.exception("atlas image object delete failed name=%s", entry)
