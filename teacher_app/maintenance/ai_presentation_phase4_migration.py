"""0104: presentation quality manifests, render metrics, and regenerate idempotency."""
from __future__ import annotations

from teacher_app.maintenance.migrations import _add_columns, migration


@migration("0104-ai-presentation-quality-automation")
def ai_presentation_quality_automation_104(conn, kind: str) -> None:
    payload = "JSONB" if kind == "postgres" else "TEXT"
    payload_default = "'{}'::jsonb" if kind == "postgres" else "'{}'"
    _add_columns(
        conn,
        kind,
        "ai_presentations",
        {
            "quality_manifest_json": f"quality_manifest_json {payload} NOT NULL DEFAULT {payload_default}",
            "render_metrics_json": f"render_metrics_json {payload} NOT NULL DEFAULT {payload_default}",
            "render_ruleset_version": "render_ruleset_version TEXT NOT NULL DEFAULT ''",
        },
    )
    _add_columns(
        conn,
        kind,
        "ai_presentation_jobs",
        {"idempotency_key": "idempotency_key TEXT"},
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_presentation_jobs_idempotency "
        "ON ai_presentation_jobs(idempotency_key)"
    )


__all__ = ["ai_presentation_quality_automation_104"]
