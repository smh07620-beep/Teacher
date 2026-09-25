"""Material version/retraining domain service.

This module records immutable version snapshots and advances the learner
retraining threshold without deleting historical completion evidence.
"""
from __future__ import annotations

import datetime as dt
import json
from typing import Any, Mapping

from teacher_app.common import db as common_db
from teacher_app.common.errors import ApiError
from teacher_app.materials import repository


def _fail(code: str, message: str, status: int = 400) -> ApiError:
    return ApiError(code, message, status=status)


def _actor_name(actor: Mapping[str, Any] | None) -> str:
    actor = actor or {}
    return str(actor.get("username") or actor.get("empId") or actor.get("name") or "").strip()[:120]


def _utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _snapshot(row: Mapping[str, Any]) -> str:
    payload = dict(row)
    return json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True)


def list_versions(material_id: str) -> list[dict]:
    material_id = str(material_id or "").strip()
    if not material_id:
        return []
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        rows = conn.execute(
            f"SELECT * FROM material_versions WHERE material_id={ph} ORDER BY version DESC",
            (material_id,),
        ).fetchall()
    result = []
    for row in rows:
        data = dict(row)
        raw = data.get("snapshot") or "{}"
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = {}
        data["snapshot"] = raw if isinstance(raw, dict) else {}
        data["requiresRetraining"] = bool(data.pop("requires_retraining", False))
        data["materialId"] = data.pop("material_id", "")
        data["createdAt"] = data.pop("created_at", "")
        data["createdBy"] = data.pop("created_by", "")
        data["changeReason"] = data.pop("change_reason", "")
        result.append(data)
    return result


def publish_new_version(
    material_id: str,
    *,
    actor: Mapping[str, Any] | None,
    change_reason: str,
    requires_retraining: bool,
) -> dict:
    """Advance material version and optionally require learners to retrain.

    This operation records the current canonical material row as the new version
    snapshot. Storage/file replacement should complete before this function is
    called so the snapshot represents the published state.
    """
    material_id = str(material_id or "").strip()
    reason = str(change_reason or "").strip()[:1000]
    if not material_id:
        raise _fail("MATERIAL_ID_REQUIRED", "請指定教材。")
    if not reason:
        raise _fail("MATERIAL_VERSION_REASON_REQUIRED", "請填寫版本變更原因。")

    now = _utcnow()
    created_by = _actor_name(actor)
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(f"SELECT * FROM materials WHERE id={ph}", (material_id,)).fetchone()
        if not row:
            raise _fail("MATERIAL_NOT_FOUND", "找不到教材。", 404)
        current = dict(row)
        current_version = max(1, int(current.get("current_version") or 1))
        next_version = current_version + 1
        required_version = next_version if requires_retraining else max(
            1, int(current.get("required_completion_version") or 1)
        )
        conn.execute(
            f"UPDATE materials SET current_version={ph},required_completion_version={ph},"
            f"version_updated_at={ph},version_updated_by={ph} WHERE id={ph}",
            (next_version, required_version, now, created_by, material_id),
        )
        updated = conn.execute(f"SELECT * FROM materials WHERE id={ph}", (material_id,)).fetchone()
        snapshot = _snapshot(dict(updated))
        if kind == "postgres":
            conn.execute(
                "INSERT INTO material_versions "
                "(material_id,version,snapshot,created_at,created_by,change_reason,requires_retraining) "
                "VALUES (%s,%s,%s::jsonb,%s,%s,%s,%s)",
                (material_id, next_version, snapshot, now, created_by, reason, bool(requires_retraining)),
            )
        else:
            conn.execute(
                "INSERT INTO material_versions "
                "(material_id,version,snapshot,created_at,created_by,change_reason,requires_retraining) "
                "VALUES (?,?,?,?,?,?,?)",
                (material_id, next_version, snapshot, now, created_by, reason, int(bool(requires_retraining))),
            )
    material = repository.get_material(material_id)
    return {
        "ok": True,
        "material": material,
        "version": next_version,
        "requiredCompletionVersion": required_version,
        "requiresRetraining": bool(requires_retraining),
        "changeReason": reason,
    }


def completion_is_current(material: Mapping[str, Any], completed_version: object) -> bool:
    """Return whether a learner completion satisfies the material retraining threshold."""
    required = max(1, int(material.get("requiredCompletionVersion") or 1))
    try:
        completed = max(0, int(completed_version or 0))
    except (TypeError, ValueError):
        completed = 0
    return completed >= required


__all__ = ["completion_is_current", "list_versions", "publish_new_version"]
