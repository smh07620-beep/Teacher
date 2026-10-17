"""Per-material reading rules a teacher can set (2026-10-17).

Stored in the material's storage_meta so no schema change is needed:
  optional          -> 選讀: does not block the course exam
  minSecondsPerPage -> fixed minimum seconds per page (None = automatic by text length)
  checkpointsEnabled-> False hides every checkpoint of this material from learners
"""
from __future__ import annotations

from typing import Any, Mapping

from teacher_app.common.errors import ApiError
from teacher_app.materials import repository as material_repository

MAX_SECONDS = 120


def _meta(material: Mapping[str, Any]) -> dict:
    meta = material.get("storageMeta") or {}
    return meta if isinstance(meta, dict) else {}


def read(material: Mapping[str, Any]) -> dict:
    meta = _meta(material)
    seconds = meta.get("minSecondsPerPage")
    return {
        "optional": bool(meta.get("optional")),
        "minSecondsPerPage": int(seconds) if isinstance(seconds, (int, float)) and not isinstance(seconds, bool) else None,
        "checkpointsEnabled": meta.get("checkpointsEnabled") is not False,
        "pagedMaterial": str(material.get("viewerMode") or "") in {"slides", "preview_pdf"},
    }


def checkpoints_enabled(material: Mapping[str, Any]) -> bool:
    return _meta(material).get("checkpointsEnabled") is not False


def clean(body: Mapping[str, Any]) -> dict:
    updates: dict[str, Any] = {}
    if "optional" in body:
        updates["optional"] = bool(body.get("optional"))
    if "checkpointsEnabled" in body:
        updates["checkpointsEnabled"] = bool(body.get("checkpointsEnabled"))
    if "minSecondsPerPage" in body:
        raw = body.get("minSecondsPerPage")
        if raw in (None, ""):
            updates["minSecondsPerPage"] = None
        else:
            if isinstance(raw, bool):
                raise ApiError("READING_SECONDS", "每頁最短秒數請填 0 到 120 的整數，或留白用自動。", status=400)
            try:
                value = int(raw)
            except (TypeError, ValueError):
                raise ApiError("READING_SECONDS", "每頁最短秒數請填 0 到 120 的整數，或留白用自動。", status=400) from None
            if not 0 <= value <= MAX_SECONDS:
                raise ApiError("READING_SECONDS", "每頁最短秒數請填 0 到 120 的整數，或留白用自動。", status=400)
            updates["minSecondsPerPage"] = value
    if not updates:
        raise ApiError("READING_EMPTY", "沒有要更新的設定。", status=400)
    return updates


def save(material_id: str, updates: Mapping[str, Any]) -> None:
    material_repository.merge_storage_meta(str(material_id), dict(updates))
    material_repository.invalidate_materials_cache()
