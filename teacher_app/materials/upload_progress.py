"""File-backed progress store for synchronous material processing.

The historical web host wrote one small JSON document per progress id.  Keep
that contract here so synchronous upload, background-job status and AI runtime
code can share the same canonical owner without reaching into ``legacy_host``.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
from pathlib import Path


LOGGER = logging.getLogger(__name__)


class UploadProgressStore:
    def __init__(self, paths):
        self.directory = Path(paths.upload_progress_dir)
        self.directory.mkdir(parents=True, exist_ok=True)

    def path(self, progress_id: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_-]", "", str(progress_id or ""))[:80]
        return self.directory / f"{safe}.json" if safe else Path()

    def set(
        self,
        progress_id: str,
        percent: float,
        stage: str,
        detail: str = "",
        *,
        current=0,
        total=0,
    ) -> None:
        path = self.path(progress_id)
        if not progress_id or not str(path):
            return
        data = {
            "percent": max(0, min(100, round(float(percent or 0), 1))),
            "stage": str(stage or "處理中"),
            "detail": str(detail or ""),
            "current": int(current or 0),
            "total": int(total or 0),
            "updatedAt": dt.datetime.now().isoformat(timespec="seconds"),
        }
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
        except Exception as exc:
            # Progress reporting is deliberately best-effort and must never make
            # an otherwise successful material upload fail.
            LOGGER.warning(
                "material upload progress write failed progress_id=%s error_type=%s",
                path.stem[:80],
                type(exc).__name__,
            )

    def clear(self, progress_id: str) -> None:
        path = self.path(progress_id)
        try:
            if path and path.exists():
                path.unlink()
        except Exception as exc:
            LOGGER.warning(
                "material upload progress cleanup failed progress_id=%s error_type=%s",
                path.stem[:80],
                type(exc).__name__,
            )

    def read(self, progress_id: str) -> dict | None:
        path = self.path(progress_id)
        if not path or not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            LOGGER.warning(
                "material upload progress read fallback progress_id=%s error_type=%s",
                path.stem[:80],
                type(exc).__name__,
            )
            return None
        return value if isinstance(value, dict) else None


__all__ = ["UploadProgressStore"]
