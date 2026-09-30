"""0101: reviewed PowerPoint + narration + subtitles -> video composition jobs."""
from __future__ import annotations

from teacher_app.maintenance.migrations import migration


@migration("0101-media-video-composition")
def media_video_composition_101(conn, kind: str) -> None:
    payload = "JSONB" if kind == "postgres" else "TEXT"
    payload_default = "'{}'::jsonb" if kind == "postgres" else "'{}'"

    conn.execute(
        f"CREATE TABLE IF NOT EXISTS media_video_jobs ("
        "id TEXT PRIMARY KEY,presentation_id TEXT NOT NULL,narration_material_id TEXT NOT NULL,"
        "subtitle_id TEXT NOT NULL DEFAULT '',group_key TEXT NOT NULL,training_area TEXT NOT NULL,"
        "actor_username TEXT NOT NULL,request_key TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'queued',"
        f"request_json {payload} NOT NULL DEFAULT {payload_default},"
        "progress_percent REAL NOT NULL DEFAULT 0,progress_stage TEXT NOT NULL DEFAULT '',"
        "progress_detail TEXT NOT NULL DEFAULT '',"
        f"result_json {payload} NOT NULL DEFAULT {payload_default},"
        "error TEXT NOT NULL DEFAULT '',claim_token TEXT NOT NULL DEFAULT '',attempts INTEGER NOT NULL DEFAULT 0,"
        "created_at TEXT NOT NULL,updated_at TEXT NOT NULL,started_at TEXT NOT NULL DEFAULT '',completed_at TEXT NOT NULL DEFAULT '')"
    )
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS media_videos ("
        "id TEXT PRIMARY KEY,request_key TEXT NOT NULL,presentation_id TEXT NOT NULL,"
        "narration_material_id TEXT NOT NULL,subtitle_id TEXT NOT NULL DEFAULT '',"
        "group_key TEXT NOT NULL,training_area TEXT NOT NULL,title TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'draft',"
        "artifact_backend TEXT NOT NULL DEFAULT '',artifact_storage_key TEXT NOT NULL DEFAULT '',"
        "artifact_sha256 TEXT NOT NULL DEFAULT '',artifact_bytes INTEGER NOT NULL DEFAULT 0,"
        "artifact_mime_type TEXT NOT NULL DEFAULT 'video/mp4',duration_seconds REAL NOT NULL DEFAULT 0,"
        "source_presentation_sha256 TEXT NOT NULL DEFAULT '',source_audio_key TEXT NOT NULL DEFAULT '',"
        "source_audio_version INTEGER NOT NULL DEFAULT 1,source_subtitle_updated_at TEXT NOT NULL DEFAULT '',"
        f"provenance_json {payload} NOT NULL DEFAULT {payload_default},"
        "created_by TEXT NOT NULL DEFAULT '',approved_by TEXT NOT NULL DEFAULT '',"
        "created_at TEXT NOT NULL,updated_at TEXT NOT NULL,approved_at TEXT NOT NULL DEFAULT '')"
    )

    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_media_video_jobs_request_key "
        "ON media_video_jobs(request_key)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_media_video_jobs_queue "
        "ON media_video_jobs(status,created_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_media_video_jobs_scope "
        "ON media_video_jobs(group_key,training_area,created_at)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_media_videos_request_key "
        "ON media_videos(request_key)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_media_videos_scope "
        "ON media_videos(group_key,training_area,updated_at)"
    )


__all__ = ["media_video_composition_101"]
