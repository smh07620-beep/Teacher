"""0103: layout profiles and immutable publication snapshots for AI PowerPoint."""
from __future__ import annotations

from teacher_app.maintenance.migrations import _add_columns, migration


@migration("0103-ai-presentation-publishing-workflow")
def ai_presentation_publishing_workflow_103(conn, kind: str) -> None:
    """Extend the Phase 2 records in place; historical revisions are untouched."""
    payload = "JSONB" if kind == "postgres" else "TEXT"
    payload_default = "'{}'::jsonb" if kind == "postgres" else "'{}'"
    _add_columns(
        conn,
        kind,
        "ai_presentation_templates",
        {"layout_profile_json": f"layout_profile_json {payload} NOT NULL DEFAULT {payload_default}"},
    )
    _add_columns(
        conn,
        kind,
        "ai_presentation_publications",
        {
            "presentation_family_id": "presentation_family_id TEXT NOT NULL DEFAULT ''",
            "presentation_revision_number": "presentation_revision_number INTEGER NOT NULL DEFAULT 1",
            "snapshot_json": f"snapshot_json {payload} NOT NULL DEFAULT {payload_default}",
        },
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_presentation_publications_family "
        "ON ai_presentation_publications(presentation_family_id,created_at)"
    )


__all__ = ["ai_presentation_publishing_workflow_103"]
