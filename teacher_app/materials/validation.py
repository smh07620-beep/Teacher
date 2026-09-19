"""Flask-free validation for uploaded teaching-material files."""
from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path


ALLOWED_MATERIAL_EXTENSIONS = frozenset(
    {
        ".pptx",
        ".ppt",
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".odp",
        ".odt",
        ".ods",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".mp4",
        ".webm",
        ".mov",
        ".m4v",
        ".mp3",
        ".wav",
        ".m4a",
        ".ogg",
        ".txt",
        ".csv",
        ".srt",
        ".vtt",
        ".zip",
    }
)
ZIP_EXT = frozenset({".zip", ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp"})
OLE_EXT = frozenset({".doc", ".xls", ".ppt"})
IMAGE_EXT = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp"})
MEDIA_EXT = frozenset({".mp4", ".mov", ".m4v", ".webm", ".mp3", ".wav", ".m4a", ".ogg"})
TEXT_EXT = frozenset({".txt", ".csv", ".srt", ".vtt"})
PDF_EXT = frozenset({".pdf"})


def magic_ok(ext: str, head: bytes) -> bool:
    """Return whether the leading bytes match the claimed material extension."""

    ext = str(ext or "").lower()
    if ext in ZIP_EXT:
        return head.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"))
    if ext in OLE_EXT:
        return head.startswith(bytes.fromhex("D0CF11E0A1B11AE1"))
    if ext == ".pdf":
        return head.startswith(b"%PDF-")
    if ext == ".png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if ext in {".jpg", ".jpeg"}:
        return head.startswith(b"\xff\xd8\xff")
    if ext == ".gif":
        return head.startswith((b"GIF87a", b"GIF89a"))
    if ext == ".webp":
        return len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    if ext == ".wav":
        return len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WAVE"
    if ext in {".mp4", ".mov", ".m4v", ".m4a"}:
        return len(head) >= 12 and head[4:8] == b"ftyp"
    if ext == ".webm":
        return head.startswith(b"\x1aE\xdf\xa3")
    if ext == ".ogg":
        return head.startswith(b"OggS")
    if ext == ".mp3":
        return head.startswith(b"ID3") or (
            len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0
        )
    if ext in TEXT_EXT:
        return b"\x00" not in head[:4096]
    return True


def validate_zip_bytes(raw: bytes, ext: str) -> None:
    """Reject unsafe/corrupt archives and malformed Office ZIP containers."""

    max_files = max(1, min(10000, int(os.environ.get("UPLOAD_ZIP_MAX_FILES", "2000"))))
    max_expanded = (
        max(1, min(4096, int(os.environ.get("UPLOAD_ZIP_MAX_EXPANDED_MB", "1024"))))
        * 1024
        * 1024
    )
    max_ratio = max(10, min(1000, int(os.environ.get("UPLOAD_ZIP_MAX_RATIO", "200"))))
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            infos = zf.infolist()
            if len(infos) > max_files:
                raise ValueError(f"壓縮檔檔案數超過限制（{max_files}）。")
            total = sum(max(0, info.file_size) for info in infos)
            if total > max_expanded:
                raise ValueError("壓縮檔解壓後總大小超過限制。")
            for info in infos:
                name = info.filename.replace("\\", "/")
                if name.startswith("/") or "../" in f"/{name}":
                    raise ValueError("壓縮檔包含不安全路徑。")
                if info.file_size > 0:
                    ratio = info.file_size / max(1, info.compress_size)
                    if ratio > max_ratio:
                        raise ValueError("壓縮比異常，疑似 ZIP bomb。")
            names = {info.filename for info in infos}
            if ext == ".docx" and "word/document.xml" not in names:
                raise ValueError("DOCX 結構不完整。")
            if ext == ".xlsx" and "xl/workbook.xml" not in names:
                raise ValueError("XLSX 結構不完整。")
            if ext == ".pptx" and "ppt/presentation.xml" not in names:
                raise ValueError("PPTX 結構不完整。")
    except zipfile.BadZipFile as exc:
        raise ValueError("ZIP/Office 壓縮結構損壞。") from exc


def validate_filestorage(storage) -> None:
    """Validate a Werkzeug-like FileStorage without importing Flask/Werkzeug."""

    filename = str(getattr(storage, "filename", "") or "").strip()
    if not filename:
        return
    ext = Path(filename).suffix.lower()
    stream = storage.stream
    pos = stream.tell() if hasattr(stream, "tell") else 0
    head = stream.read(8192)
    if hasattr(stream, "seek"):
        stream.seek(pos)
    if not magic_ok(ext, head):
        raise ValueError(f"檔案內容與副檔名不符：{filename}")
    if ext in ZIP_EXT:
        raw = stream.read()
        if hasattr(stream, "seek"):
            stream.seek(pos)
        validate_zip_bytes(raw, ext)


# Compatibility aliases for legacy imports while callers converge.
_magic_ok = magic_ok
_validate_zip_bytes = validate_zip_bytes
