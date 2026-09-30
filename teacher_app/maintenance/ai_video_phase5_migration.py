"""0105: video quality manifests, render metrics, and generation idempotency."""
from __future__ import annotations

from teacher_app.maintenance.migrations import _add_columns, migration


@migration("0105-ai-video-production-hardening")
def ai_video_production_hardening_105(conn, kind: str) -> None:
    payload = "JSONB" if kind == "postgres" else "TEXT"
    payload_default = "'{}'::jsonb" if kind == "postgres" else "'{}'"
    _add_columns(
        conn,
        kind,
        "ai_video_jobs",
        {"idempotency_key": "idempotency_key TEXT"},
    )
    _add_columns(
        conn,
        kind,
        "ai_presentation_videos",
        {
            "quality_manifest_json": f"quality_manifest_json {payload} NOT NULL DEFAULT {payload_default}",
            "render_metrics_json": f"render_metrics_json {payload} NOT NULL DEFAULT {payload_default}",
            "render_ruleset_version": "render_ruleset_version TEXT NOT NULL DEFAULT ''",
            "frame_renderer": "frame_renderer TEXT NOT NULL DEFAULT ''",
        },
    )
    _add_columns(
        conn,
        kind,
        "ai_video_publications",
        {
            "video_family_id": "video_family_id TEXT NOT NULL DEFAULT ''",
            "video_revision_number": "video_revision_number INTEGER NOT NULL DEFAULT 1",
            "snapshot_json": f"snapshot_json {payload} NOT NULL DEFAULT {payload_default}",
        },
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_video_jobs_idempotency "
        "ON ai_video_jobs(idempotency_key)"
    )


__all__ = ["ai_video_production_hardening_105"]
