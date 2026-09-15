"""Teacher 6.4 upload signature and archive-safety validation."""
from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path
from typing import BinaryIO

from flask import jsonify, request

ZIP_EXT = {".zip", ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp"}
OLE_EXT = {".doc", ".xls", ".ppt"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
MEDIA_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mp3", ".wav", ".m4a", ".ogg"}
TEXT_EXT = {".txt", ".csv", ".srt", ".vtt"}
PDF_EXT = {".pdf"}


def _magic_ok(ext: str, head: bytes) -> bool:
    if ext in ZIP_EXT:
        return head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06") or head.startswith(b"PK\x07\x08")
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
        return head.startswith(b"ID3") or (len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0)
    if ext in TEXT_EXT:
        return b"\x00" not in head[:4096]
    return True


def _validate_zip_bytes(raw: bytes, ext: str) -> None:
    max_files = max(1, min(10000, int(os.environ.get("UPLOAD_ZIP_MAX_FILES", "2000"))))
    max_expanded = max(1, min(4096, int(os.environ.get("UPLOAD_ZIP_MAX_EXPANDED_MB", "1024")))) * 1024 * 1024
    max_ratio = max(10, min(1000, int(os.environ.get("UPLOAD_ZIP_MAX_RATIO", "200"))))
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            infos = zf.infolist()
            if len(infos) > max_files:
                raise ValueError(f"壓縮檔檔案數超過限制（{max_files}）。")
            total = sum(max(0, i.file_size) for i in infos)
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
            names = {i.filename for i in infos}
            if ext == ".docx" and "word/document.xml" not in names:
                raise ValueError("DOCX 結構不完整。")
            if ext == ".xlsx" and "xl/workbook.xml" not in names:
                raise ValueError("XLSX 結構不完整。")
            if ext == ".pptx" and "ppt/presentation.xml" not in names:
                raise ValueError("PPTX 結構不完整。")
    except zipfile.BadZipFile as exc:
        raise ValueError("ZIP/Office 壓縮結構損壞。") from exc


def validate_filestorage(storage) -> None:
    filename = str(getattr(storage, "filename", "") or "").strip()
    if not filename:
        return
    ext = Path(filename).suffix.lower()
    stream = storage.stream
    pos = stream.tell() if hasattr(stream, "tell") else 0
    head = stream.read(8192)
    if hasattr(stream, "seek"):
        stream.seek(pos)
    if not _magic_ok(ext, head):
        raise ValueError(f"檔案內容與副檔名不符：{filename}")
    if ext in ZIP_EXT:
        # Archive inspection requires the full upload, then rewinds for the legacy handler.
        raw = stream.read()
        if hasattr(stream, "seek"):
            stream.seek(pos)
        _validate_zip_bytes(raw, ext)


def register_upload_hardening(base):
    app = base.app
    if app.extensions.get("teacher_upload_hardening_registered"):
        return app
    app.extensions["teacher_upload_hardening_registered"] = True

    @app.before_request
    def validate_uploaded_files():
        if request.method not in {"POST", "PUT", "PATCH"}:
            return None
        if not request.files:
            return None
        try:
            for storage in request.files.values():
                validate_filestorage(storage)
        except Exception as exc:
            return jsonify({"error": f"上傳檔案安全檢查失敗：{str(exc)[:400]}"}), 400
        return None

    return app
