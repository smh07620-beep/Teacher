"""Immutable ledger for published AI derivatives of canonical material versions."""
from __future__ import annotations

import datetime as dt
import json
import re
import uuid
from typing import Any, Mapping

from teacher_app.common import db as common_db


DERIVATIVE_TYPES = {"presentation", "video"}
DURABLE_BACKENDS = {"r2", "oci", "gdrive", "mega", "local"}
MIME_BY_TYPE = {
    "presentation": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "video": "video/mp4",
}


def _decode(value: Any) -> dict:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str) and value:
        try:
            data = json.loads(value)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def _project(row) -> dict | None:
    if not row:
        return None
    item = dict(row)
    return {
        "id": str(item.get("id") or ""),
        "materialId": str(item.get("material_id") or ""),
        "materialVersion": max(1, int(item.get("material_version") or 1)),
        "type": str(item.get("derivative_type") or ""),
        "derivativeId": str(item.get("derivative_id") or ""),
        "sourcePresentationId": str(item.get("source_presentation_id") or ""),
        "sourcePresentationRevision": max(0, int(item.get("source_presentation_revision") or 0)),
        "artifactBackend": str(item.get("artifact_backend") or ""),
        "artifactStorageKey": str(item.get("artifact_storage_key") or ""),
        "artifactSha256": str(item.get("artifact_sha256") or ""),
        "artifactBytes": max(0, int(item.get("artifact_bytes") or 0)),
        "artifactMimeType": str(item.get("artifact_mime_type") or ""),
        "receiptKey": str(item.get("receipt_key") or ""),
        "provenance": _decode(item.get("provenance_json")),
        "publishedBy": str(item.get("published_by") or ""),
        "publishedAt": str(item.get("published_at") or ""),
    }


def get_by_derivative(material_id: str, derivative_type: str, derivative_id: str) -> dict | None:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT * FROM material_derivative_publications "
            f"WHERE material_id={ph} AND derivative_type={ph} AND derivative_id={ph}",
            (str(material_id or ""), str(derivative_type or ""), str(derivative_id or "")),
        ).fetchone()
    return _project(row)


def list_for_material(material_id: str) -> list[dict]:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        rows = conn.execute(
            f"SELECT * FROM material_derivative_publications "
            f"WHERE material_id={ph} ORDER BY material_version DESC,published_at DESC",
            (str(material_id or ""),),
        ).fetchall()
    return [_project(row) for row in rows if row]


def list_for_material_version(material_id: str, material_version: int) -> list[dict]:
    version = max(1, int(material_version or 1))
    return [
        item for item in list_for_material(material_id)
        if int(item.get("materialVersion") or 0) == version
    ]


def record_publication(
    *,
    material_id: str,
    derivative_type: str,
    derivative_id: str,
    source_presentation_id: str = "",
    source_presentation_revision: int = 0,
    artifact: Mapping[str, Any],
    receipt_key: str,
    provenance: Mapping[str, Any] | None,
    published_by: str,
) -> dict:
    material_id = str(material_id or "").strip()
    derivative_type = str(derivative_type or "").strip().lower()
    derivative_id = str(derivative_id or "").strip()
    if derivative_type not in DERIVATIVE_TYPES:
        raise ValueError("不支援的教材衍生內容類型。")
    if not material_id or not derivative_id:
        raise ValueError("教材衍生內容缺少 canonical material 或 derivative id。")

    backend = str(artifact.get("backend") or "").strip().lower()
    key = str(artifact.get("key") or "").strip()
    digest = str(artifact.get("sha256") or "").strip().lower()
    size = int(artifact.get("byteSize") or 0)
    mime = str(artifact.get("mimeType") or "").strip()
    if (
        backend not in DURABLE_BACKENDS
        or not key
        or not re.fullmatch(r"[0-9a-f]{64}", digest)
        or size <= 0
        or mime != MIME_BY_TYPE[derivative_type]
    ):
        raise ValueError("教材衍生內容 durable artifact metadata 不完整。")

    existing = get_by_derivative(material_id, derivative_type, derivative_id)
    if existing:
        return existing

    stamp = dt.datetime.now(dt.timezone.utc).isoformat()
    provenance_json = json.dumps(
        dict(provenance or {}),
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        select_sql = f"SELECT current_version FROM materials WHERE id={ph}"
        if kind == "postgres":
            select_sql += " FOR UPDATE"
        material = conn.execute(select_sql, (material_id,)).fetchone()
        if not material:
            raise ValueError("找不到 canonical 教材，拒絕建立衍生內容 ledger。")
        material_version = max(1, int(dict(material).get("current_version") or 1))

        row = conn.execute(
            f"SELECT * FROM material_derivative_publications "
            f"WHERE material_id={ph} AND derivative_type={ph} AND derivative_id={ph}",
            (material_id, derivative_type, derivative_id),
        ).fetchone()
        if row:
            return _project(row) or {}

        derivative_pk = "deriv-" + uuid.uuid4().hex
        json_mark = f"{ph}::jsonb" if kind == "postgres" else ph
        prefix = "INSERT INTO" if kind == "postgres" else "INSERT OR IGNORE INTO"
        suffix = (
            " ON CONFLICT(material_id,derivative_type,derivative_id) DO NOTHING"
            if kind == "postgres"
            else ""
        )
        conn.execute(
            prefix
            + " material_derivative_publications("
            "id,material_id,material_version,derivative_type,derivative_id,"
            "source_presentation_id,source_presentation_revision,"
            "artifact_backend,artifact_storage_key,artifact_sha256,artifact_bytes,artifact_mime_type,"
            "receipt_key,provenance_json,published_by,published_at"
            ") VALUES("
            + ",".join([ph] * 13)
            + f",{json_mark},{ph},{ph})"
            + suffix,
            (
                derivative_pk,
                material_id,
                material_version,
                derivative_type,
                derivative_id,
                str(source_presentation_id or "")[:160],
                max(0, int(source_presentation_revision or 0)),
                backend,
                key,
                digest,
                size,
                mime,
                str(receipt_key or "")[:255],
                provenance_json,
                str(published_by or "")[:120],
                stamp,
            ),
        )
        row = conn.execute(
            f"SELECT * FROM material_derivative_publications "
            f"WHERE material_id={ph} AND derivative_type={ph} AND derivative_id={ph}",
            (material_id, derivative_type, derivative_id),
        ).fetchone()
    result = _project(row)
    if not result:
        raise RuntimeError("教材衍生內容 ledger 寫入驗證失敗。")
    return result


__all__ = [
    "DERIVATIVE_TYPES",
    "get_by_derivative",
    "list_for_material",
    "list_for_material_version",
    "record_publication",
]
