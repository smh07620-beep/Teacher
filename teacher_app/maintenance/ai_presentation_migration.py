"""0099/0100: AI PowerPoint generation and production hardening.

0099 creates the first presentation/job/template records. 0100 is deliberately
additive so databases that already ran the earlier local-only 0099 prototype can
be upgraded without replacing historical rows.
"""
from __future__ import annotations

from teacher_app.maintenance.migrations import _add_columns, migration


@migration("0099-ai-presentations")
def ai_presentations_99(conn, kind: str) -> None:
    payload = "JSONB" if kind == "postgres" else "TEXT"
    payload_default = "'{}'::jsonb" if kind == "postgres" else "'{}'"
    list_default = "'[]'::jsonb" if kind == "postgres" else "'[]'"
    boolean = "BOOLEAN" if kind == "postgres" else "INTEGER"
    default_true = "TRUE" if kind == "postgres" else "1"

    conn.execute(
        f"CREATE TABLE IF NOT EXISTS ai_presentation_templates ("
        "id TEXT PRIMARY KEY,name TEXT NOT NULL,group_key TEXT NOT NULL,training_area TEXT NOT NULL,"
        f"active {boolean} NOT NULL DEFAULT {default_true},"
        "storage_backend TEXT NOT NULL DEFAULT 'local',storage_key TEXT NOT NULL DEFAULT '',"
        "storage_filename TEXT NOT NULL DEFAULT '',sha256 TEXT NOT NULL DEFAULT '',"
        "byte_size BIGINT NOT NULL DEFAULT 0,mime_type TEXT NOT NULL DEFAULT '',"
        "created_by TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL)"
    )
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS ai_presentation_jobs ("
        "id TEXT PRIMARY KEY,draft_id TEXT NOT NULL,template_id TEXT NOT NULL DEFAULT '',"
        "group_key TEXT NOT NULL,training_area TEXT NOT NULL,actor_username TEXT NOT NULL,"
        "status TEXT NOT NULL DEFAULT 'queued',"
        f"request_json {payload} NOT NULL DEFAULT {payload_default},"
        "progress_percent REAL NOT NULL DEFAULT 0,progress_stage TEXT NOT NULL DEFAULT '',"
        "progress_detail TEXT NOT NULL DEFAULT '',"
        f"result_json {payload} NOT NULL DEFAULT {payload_default},"
        "error TEXT NOT NULL DEFAULT '',claim_token TEXT NOT NULL DEFAULT '',attempts INTEGER NOT NULL DEFAULT 0,"
        "created_at TEXT NOT NULL,updated_at TEXT NOT NULL,started_at TEXT NOT NULL DEFAULT '',"
        "completed_at TEXT NOT NULL DEFAULT '')"
    )
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS ai_presentations ("
        "id TEXT PRIMARY KEY,material_id TEXT NOT NULL,draft_id TEXT NOT NULL,template_id TEXT NOT NULL DEFAULT '',"
        "group_key TEXT NOT NULL,training_area TEXT NOT NULL,title TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'draft',"
        f"slides_json {payload} NOT NULL DEFAULT {list_default},"
        "artifact_backend TEXT NOT NULL DEFAULT 'local',artifact_storage_key TEXT NOT NULL DEFAULT '',"
        "artifact_storage_filename TEXT NOT NULL DEFAULT '',artifact_sha256 TEXT NOT NULL DEFAULT '',"
        "artifact_bytes BIGINT NOT NULL DEFAULT 0,artifact_mime_type TEXT NOT NULL DEFAULT '',"
        "provider TEXT NOT NULL DEFAULT '',model TEXT NOT NULL DEFAULT '',source_job_id TEXT NOT NULL DEFAULT '',"
        "created_by TEXT NOT NULL DEFAULT '',updated_by TEXT NOT NULL DEFAULT '',approved_by TEXT NOT NULL DEFAULT '',"
        "approved_at TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_presentation_jobs_queue "
        "ON ai_presentation_jobs(status,created_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_presentations_scope "
        "ON ai_presentations(group_key,training_area,updated_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_presentations_source_job "
        "ON ai_presentations(source_job_id,created_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_presentation_templates_scope "
        "ON ai_presentation_templates(group_key,training_area,active,updated_at)"
    )


@migration("0100-ai-presentation-production-hardening")
def ai_presentation_production_hardening_100(conn, kind: str) -> None:
    payload = "JSONB" if kind == "postgres" else "TEXT"
    payload_default = "'{}'::jsonb" if kind == "postgres" else "'{}'"

    # Existing 0099 installations are extended in-place. Never rewrite the
    # artifact/template location that an administrator already published.
    _add_columns(
        conn,
        kind,
        "ai_presentation_templates",
        {
            "storage_backend": "storage_backend TEXT NOT NULL DEFAULT 'local'",
            "storage_key": "storage_key TEXT NOT NULL DEFAULT ''",
            "storage_filename": "storage_filename TEXT NOT NULL DEFAULT ''",
            "sha256": "sha256 TEXT NOT NULL DEFAULT ''",
            "byte_size": "byte_size BIGINT NOT NULL DEFAULT 0",
            "mime_type": "mime_type TEXT NOT NULL DEFAULT ''",
        },
    )
    _add_columns(
        conn,
        kind,
        "ai_presentations",
        {
            "presentation_family_id": "presentation_family_id TEXT NOT NULL DEFAULT ''",
            "parent_version_id": "parent_version_id TEXT NOT NULL DEFAULT ''",
            "revision_number": "revision_number INTEGER NOT NULL DEFAULT 1",
            "artifact_backend": "artifact_backend TEXT NOT NULL DEFAULT 'local'",
            "artifact_storage_key": "artifact_storage_key TEXT NOT NULL DEFAULT ''",
            "artifact_storage_filename": "artifact_storage_filename TEXT NOT NULL DEFAULT ''",
            "artifact_sha256": "artifact_sha256 TEXT NOT NULL DEFAULT ''",
            "artifact_bytes": "artifact_bytes BIGINT NOT NULL DEFAULT 0",
            "artifact_mime_type": "artifact_mime_type TEXT NOT NULL DEFAULT ''",
            "published_at": "published_at TEXT NOT NULL DEFAULT ''",
        },
    )
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS ai_presentation_publications ("
        "id TEXT PRIMARY KEY,presentation_id TEXT NOT NULL,publication_material_id TEXT NOT NULL,"
        "receipt_key TEXT NOT NULL UNIQUE,"
        f"receipt_json {payload} NOT NULL DEFAULT {payload_default},"
        "created_by TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,"
        "UNIQUE(presentation_id,publication_material_id))"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_presentations_family "
        "ON ai_presentations(presentation_family_id,revision_number)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_presentation_publications_presentation "
        "ON ai_presentation_publications(presentation_id,created_at)"
    )

__all__ = [
    "ai_presentations_99",
    "ai_presentation_production_hardening_100",
]
