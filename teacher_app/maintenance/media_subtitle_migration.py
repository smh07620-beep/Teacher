"""0098: persistent AI subtitle generation jobs and teacher-reviewed captions."""
from __future__ import annotations

from teacher_app.maintenance.migrations import migration


@migration("0098-media-subtitles")
def media_subtitles_98(conn, kind: str) -> None:
    payload = "JSONB" if kind == "postgres" else "TEXT"
    payload_default = "'{}'::jsonb" if kind == "postgres" else "'{}'"
    boolean = "BOOLEAN" if kind == "postgres" else "INTEGER"
    default_false = "FALSE" if kind == "postgres" else "0"

    conn.execute(
        f"CREATE TABLE IF NOT EXISTS media_subtitle_jobs ("
        "id TEXT PRIMARY KEY,material_id TEXT NOT NULL,group_key TEXT NOT NULL,training_area TEXT NOT NULL,"
        "actor_username TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'queued',"
        f"request_json {payload} NOT NULL DEFAULT {payload_default},"
        "progress_percent REAL NOT NULL DEFAULT 0,progress_stage TEXT NOT NULL DEFAULT '',"
        "progress_detail TEXT NOT NULL DEFAULT '',"
        f"result_json {payload} NOT NULL DEFAULT {payload_default},"
        "error TEXT NOT NULL DEFAULT '',claim_token TEXT NOT NULL DEFAULT '',attempts INTEGER NOT NULL DEFAULT 0,"
        "created_at TEXT NOT NULL,updated_at TEXT NOT NULL,started_at TEXT NOT NULL DEFAULT '',completed_at TEXT NOT NULL DEFAULT '')"
    )
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS media_subtitles ("
        "id TEXT PRIMARY KEY,material_id TEXT NOT NULL,group_key TEXT NOT NULL,training_area TEXT NOT NULL,"
        "language TEXT NOT NULL DEFAULT 'zh-TW',label TEXT NOT NULL DEFAULT '繁體中文字幕',"
        "status TEXT NOT NULL DEFAULT 'draft',vtt_text TEXT NOT NULL DEFAULT '',srt_text TEXT NOT NULL DEFAULT '',"
        "transcript_text TEXT NOT NULL DEFAULT '',provider TEXT NOT NULL DEFAULT '',model TEXT NOT NULL DEFAULT '',"
        f"fallback_used {boolean} NOT NULL DEFAULT {default_false},source_version INTEGER NOT NULL DEFAULT 1,"
        "source_sha256 TEXT NOT NULL DEFAULT '',source_kind TEXT NOT NULL DEFAULT '',source_locator TEXT NOT NULL DEFAULT '',"
        "source_job_id TEXT NOT NULL DEFAULT '',created_by TEXT NOT NULL DEFAULT '',updated_by TEXT NOT NULL DEFAULT '',"
        "approved_by TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,approved_at TEXT NOT NULL DEFAULT '')"
    )

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_media_subtitle_jobs_queue "
        "ON media_subtitle_jobs(status,created_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_media_subtitle_jobs_actor "
        "ON media_subtitle_jobs(actor_username,created_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_media_subtitle_jobs_scope "
        "ON media_subtitle_jobs(group_key,training_area,created_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_media_subtitles_material "
        "ON media_subtitles(material_id,language,status,updated_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_media_subtitles_scope "
        "ON media_subtitles(group_key,training_area,updated_at)"
    )


__all__ = ["media_subtitles_98"]
