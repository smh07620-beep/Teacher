"""0101: durable, teacher-reviewed AI presentation video jobs."""
from __future__ import annotations

from teacher_app.maintenance.migrations import migration


@migration("0101-ai-presentation-videos")
def ai_presentation_videos_101(conn, kind: str) -> None:
    payload = "JSONB" if kind == "postgres" else "TEXT"
    default = "'{}'::jsonb" if kind == "postgres" else "'{}'"
    timeline_default = "'[]'::jsonb" if kind == "postgres" else "'[]'"
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS ai_video_jobs ("
        "id TEXT PRIMARY KEY,presentation_id TEXT NOT NULL,presentation_family_id TEXT NOT NULL DEFAULT '',"
        "presentation_revision INTEGER NOT NULL DEFAULT 1,group_key TEXT NOT NULL,training_area TEXT NOT NULL,"
        "actor_username TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'queued',"
        f"request_json {payload} NOT NULL DEFAULT {default},progress_percent REAL NOT NULL DEFAULT 0,"
        "progress_stage TEXT NOT NULL DEFAULT '',progress_detail TEXT NOT NULL DEFAULT '',"
        f"result_json {payload} NOT NULL DEFAULT {default},error TEXT NOT NULL DEFAULT '',"
        "claim_token TEXT NOT NULL DEFAULT '',attempts INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,"
        "updated_at TEXT NOT NULL,started_at TEXT NOT NULL DEFAULT '',completed_at TEXT NOT NULL DEFAULT '')"
    )
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS ai_presentation_videos ("
        "id TEXT PRIMARY KEY,video_family_id TEXT NOT NULL DEFAULT '',parent_revision_id TEXT NOT NULL DEFAULT '',"
        "revision_number INTEGER NOT NULL DEFAULT 1,presentation_id TEXT NOT NULL,presentation_family_id TEXT NOT NULL DEFAULT '',"
        "presentation_revision INTEGER NOT NULL DEFAULT 1,presentation_sha256 TEXT NOT NULL DEFAULT '',"
        "group_key TEXT NOT NULL,training_area TEXT NOT NULL,title TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'draft',"
        "artifact_backend TEXT NOT NULL DEFAULT '',artifact_storage_key TEXT NOT NULL DEFAULT '',"
        "artifact_storage_filename TEXT NOT NULL DEFAULT '',artifact_sha256 TEXT NOT NULL DEFAULT '',"
        "artifact_bytes BIGINT NOT NULL DEFAULT 0,artifact_mime_type TEXT NOT NULL DEFAULT '',duration_seconds REAL NOT NULL DEFAULT 0,"
        f"timeline_json {payload} NOT NULL DEFAULT {timeline_default},vtt_text TEXT NOT NULL DEFAULT '',srt_text TEXT NOT NULL DEFAULT '',"
        "tts_provider TEXT NOT NULL DEFAULT '',tts_model TEXT NOT NULL DEFAULT '',tts_voice TEXT NOT NULL DEFAULT '',"
        "source_job_id TEXT NOT NULL DEFAULT '',created_by TEXT NOT NULL DEFAULT '',updated_by TEXT NOT NULL DEFAULT '',"
        "approved_by TEXT NOT NULL DEFAULT '',approved_at TEXT NOT NULL DEFAULT '',published_at TEXT NOT NULL DEFAULT '',"
        "created_at TEXT NOT NULL,updated_at TEXT NOT NULL)"
    )
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS ai_video_publications (id TEXT PRIMARY KEY,video_id TEXT NOT NULL,receipt_key TEXT NOT NULL UNIQUE,"
        f"receipt_json {payload} NOT NULL DEFAULT {default},created_by TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,UNIQUE(video_id))"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_video_jobs_queue ON ai_video_jobs(status,created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_video_jobs_scope ON ai_video_jobs(group_key,training_area,created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_presentation_videos_scope ON ai_presentation_videos(group_key,training_area,updated_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_presentation_videos_presentation ON ai_presentation_videos(presentation_id,revision_number)")


# Register additive Phase 5 migration whenever the canonical video migration module is imported.
from teacher_app.maintenance import ai_video_phase5_migration as _ai_video_phase5_migration  # noqa: E402,F401


__all__ = ["ai_presentation_videos_101"]
