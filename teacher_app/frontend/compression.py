"""gzip for text responses, so the free hosting plan's outbound quota lasts longer.

Only text-like types (HTML, JSON, JS, CSS, SVG, plain text, CSV) are compressed.
Images, WebP slides, video, audio, PDF, Office files and ZIP are already compressed
or are streamed/range-served, so they are never touched.

Compression is skipped when it could break something: a response that is already
encoded, a partial (206) or empty/redirect response, a client without gzip support,
or a response too small to benefit.  ``Vary: Accept-Encoding`` is always added to
compressible responses so shared caches keep the two variants apart.
"""
from __future__ import annotations

import gzip
import os
from collections import OrderedDict
from threading import Lock

from flask import request

COMPRESSIBLE_MIMETYPES = frozenset(
    {
        "text/html",
        "text/css",
        "text/plain",
        "text/csv",
        "text/javascript",
        "application/javascript",
        "application/json",
        "application/xml",
        "text/xml",
        "image/svg+xml",
    }
)
MIN_BYTES = 1024
# Static files are served by send_file as a stream; only buffer them when small enough.
MAX_BUFFERED_BYTES = 8 * 1024 * 1024
_CACHE_MAX_ENTRIES = 64
_CACHE_MAX_BYTES = 8 * 1024 * 1024


def _enabled() -> bool:
    return os.environ.get("RESPONSE_COMPRESSION", "true").strip().lower() not in {"0", "false", "no", "off"}


def _accepts_gzip() -> bool:
    header = request.headers.get("Accept-Encoding", "")
    for part in header.split(","):
        token, _, params = part.strip().partition(";")
        if token.strip().lower() not in {"gzip", "x-gzip"}:
            continue
        quality = 1.0
        params = params.strip().lower().replace(" ", "")
        if params.startswith("q="):
            try:
                quality = float(params[2:])
            except ValueError:
                quality = 1.0
        return quality > 0
    return False


class _GzipCache:
    """Tiny LRU so an unchanged static file is not recompressed on every request."""

    def __init__(self) -> None:
        self._items: OrderedDict[str, bytes] = OrderedDict()
        self._bytes = 0
        self._lock = Lock()

    def get(self, key: str) -> bytes | None:
        with self._lock:
            value = self._items.get(key)
            if value is not None:
                self._items.move_to_end(key)
            return value

    def put(self, key: str, value: bytes) -> None:
        if len(value) > _CACHE_MAX_BYTES // 4:
            return
        with self._lock:
            old = self._items.pop(key, None)
            if old is not None:
                self._bytes -= len(old)
            self._items[key] = value
            self._bytes += len(value)
            while len(self._items) > _CACHE_MAX_ENTRIES or self._bytes > _CACHE_MAX_BYTES:
                _, dropped = self._items.popitem(last=False)
                self._bytes -= len(dropped)


def register_response_compression(app):
    if app.extensions.get("teacher_response_compression_registered"):
        return app
    cache = _GzipCache()

    @app.after_request
    def compress_text_response(response):
        if not _enabled():
            return response
        if response.status_code in (204, 206, 304) or response.status_code < 200 or response.status_code >= 300:
            return response
        if request.method == "HEAD":
            return response
        mimetype = (response.mimetype or "").lower()
        if mimetype not in COMPRESSIBLE_MIMETYPES:
            return response
        # From here on the response is compressible: always tell caches it varies.
        vary = response.headers.get("Vary", "")
        if "accept-encoding" not in vary.lower():
            response.headers["Vary"] = f"{vary}, Accept-Encoding" if vary else "Accept-Encoding"
        if response.headers.get("Content-Encoding") or response.headers.get("Content-Range"):
            return response
        if response.is_streamed and not response.direct_passthrough:
            return response
        if not _accepts_gzip():
            return response
        length = response.content_length
        if length is not None and (length < MIN_BYTES or length > MAX_BUFFERED_BYTES):
            return response

        etag = response.headers.get("ETag", "")
        cache_key = f"{request.path}|{etag}" if etag and not etag.startswith("W/") else ""
        if response.direct_passthrough:
            # send_file / send_from_directory: read the (small) file once, then serve gzip.
            if length is None:
                return response
            cached = cache.get(cache_key) if cache_key else None
            if cached is None:
                response.direct_passthrough = False
                try:
                    raw = b"".join(response.iter_encoded())
                finally:
                    response.close()  # release the open file handle
                cached = gzip.compress(raw, compresslevel=6, mtime=0)
                if cache_key:
                    cache.put(cache_key, cached)
            data = cached
        else:
            raw = response.get_data()
            if len(raw) < MIN_BYTES:
                return response
            data = gzip.compress(raw, compresslevel=6, mtime=0)

        response.set_data(data)
        response.headers["Content-Encoding"] = "gzip"
        response.headers["Content-Length"] = str(len(data))
        if etag and not etag.startswith("W/"):
            # A strong validator no longer describes the bytes on the wire.
            response.headers["ETag"] = f"W/{etag}"
        return response

    app.extensions["teacher_response_compression_registered"] = True
    return app


__all__ = ["COMPRESSIBLE_MIMETYPES", "register_response_compression"]
