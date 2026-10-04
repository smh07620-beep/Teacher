"""0115: immutable derivative publications linked to canonical material versions."""
from __future__ import annotations

from teacher_app.maintenance.migrations import migration


@migration("0115-material-derivative-publications")
def material_derivative_publications_115(conn, kind: str) -> None:
    payload = "JSONB" if kind == "postgres" else "TEXT"
    payload_default = "'{}'::jsonb" if kind == "postgres" else "'{}'"
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS material_derivative_publications ("
        "id TEXT PRIMARY KEY,"
        "material_id TEXT NOT NULL,"
        "material_version INTEGER NOT NULL,"
        "derivative_type TEXT NOT NULL,"
        "derivative_id TEXT NOT NULL,"
        "source_presentation_id TEXT NOT NULL DEFAULT '',"
        "source_presentation_revision INTEGER NOT NULL DEFAULT 0,"
        "artifact_backend TEXT NOT NULL DEFAULT '',"
        "artifact_storage_key TEXT NOT NULL DEFAULT '',"
        "artifact_sha256 TEXT NOT NULL DEFAULT '',"
        "artifact_bytes BIGINT NOT NULL DEFAULT 0,"
        "artifact_mime_type TEXT NOT NULL DEFAULT '',"
        "receipt_key TEXT NOT NULL DEFAULT '',"
        f"provenance_json {payload} NOT NULL DEFAULT {payload_default},"
        "published_by TEXT NOT NULL DEFAULT '',"
        "published_at TEXT NOT NULL,"
        "UNIQUE(material_id,derivative_type,derivative_id)"
        ")"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_material_derivative_version "
        "ON material_derivative_publications(material_id,material_version,published_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_material_derivative_source_presentation "
        "ON material_derivative_publications(source_presentation_id,published_at)"
    )


__all__ = ["material_derivative_publications_115"]
