"""0094: persistent media-script drafts and asynchronous generation jobs."""
from __future__ import annotations

from teacher_app.maintenance.migrations import migration


@migration("0094-media-script-jobs")
def media_script_jobs_94(conn, kind: str) -> None:
    payload = "JSONB" if kind == "postgres" else "TEXT"
    payload_default = "'{}'::jsonb" if kind == "postgres" else "'{}'"
    chunks_default = "'[]'::jsonb" if kind == "postgres" else "'[]'"

    conn.execute(
        f"CREATE TABLE IF NOT EXISTS media_script_jobs ("
        "id TEXT PRIMARY KEY,material_id TEXT NOT NULL,group_key TEXT NOT NULL,"
        "training_area TEXT NOT NULL,actor_username TEXT NOT NULL,"
        "status TEXT NOT NULL DEFAULT 'queued',"
        f"request_json {payload} NOT NULL DEFAULT {payload_default},"
        "progress_percent REAL NOT NULL DEFAULT 0,progress_stage TEXT NOT NULL DEFAULT '',"
        "progress_detail TEXT NOT NULL DEFAULT '',"
        f"result_json {payload} NOT NULL DEFAULT {payload_default},"
        "error TEXT NOT NULL DEFAULT '',claim_token TEXT NOT NULL DEFAULT '',attempts INTEGER NOT NULL DEFAULT 0,"
        "created_at TEXT NOT NULL,updated_at TEXT NOT NULL,started_at TEXT NOT NULL DEFAULT '',completed_at TEXT NOT NULL DEFAULT '')"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_media_script_jobs_queue "
        "ON media_script_jobs(status,created_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_media_script_jobs_actor "
        "ON media_script_jobs(actor_username,created_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_media_script_jobs_scope "
        "ON media_script_jobs(group_key,training_area,created_at)"
    )

    conn.execute(
        f"CREATE TABLE IF NOT EXISTS media_scripts ("
        "id TEXT PRIMARY KEY,material_id TEXT NOT NULL,group_key TEXT NOT NULL,training_area TEXT NOT NULL,"
        "title TEXT NOT NULL,body TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'draft',"
        "source_job_id TEXT NOT NULL DEFAULT '',"
        f"source_chunks_json {payload} NOT NULL DEFAULT {chunks_default},"
        "created_by TEXT NOT NULL,updated_by TEXT NOT NULL,approved_by TEXT NOT NULL DEFAULT '',"
        "created_at TEXT NOT NULL,updated_at TEXT NOT NULL,approved_at TEXT NOT NULL DEFAULT '')"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_media_scripts_material "
        "ON media_scripts(material_id,status,updated_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_media_scripts_scope "
        "ON media_scripts(group_key,training_area,updated_at)"
    )


__all__ = ["media_script_jobs_94"]
