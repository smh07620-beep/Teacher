"""0095: persistent AI narration generation jobs."""
from __future__ import annotations

from teacher_app.maintenance.migrations import migration


@migration("0095-media-audio-jobs")
def media_audio_jobs_95(conn, kind: str) -> None:
    payload = "JSONB" if kind == "postgres" else "TEXT"
    payload_default = "'{}'::jsonb" if kind == "postgres" else "'{}'"
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS media_audio_jobs ("
        "id TEXT PRIMARY KEY,script_id TEXT NOT NULL,material_id TEXT NOT NULL,"
        "group_key TEXT NOT NULL,training_area TEXT NOT NULL,actor_username TEXT NOT NULL,"
        "status TEXT NOT NULL DEFAULT 'queued',"
        f"request_json {payload} NOT NULL DEFAULT {payload_default},"
        "progress_percent REAL NOT NULL DEFAULT 0,progress_stage TEXT NOT NULL DEFAULT '',"
        "progress_detail TEXT NOT NULL DEFAULT '',"
        f"result_json {payload} NOT NULL DEFAULT {payload_default},"
        "error TEXT NOT NULL DEFAULT '',claim_token TEXT NOT NULL DEFAULT '',attempts INTEGER NOT NULL DEFAULT 0,"
        "created_at TEXT NOT NULL,updated_at TEXT NOT NULL,started_at TEXT NOT NULL DEFAULT '',completed_at TEXT NOT NULL DEFAULT '')"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_media_audio_jobs_queue "
        "ON media_audio_jobs(status,created_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_media_audio_jobs_actor "
        "ON media_audio_jobs(actor_username,created_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_media_audio_jobs_script "
        "ON media_audio_jobs(script_id,created_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_media_audio_jobs_scope "
        "ON media_audio_jobs(group_key,training_area,created_at)"
    )


__all__ = ["media_audio_jobs_95"]
