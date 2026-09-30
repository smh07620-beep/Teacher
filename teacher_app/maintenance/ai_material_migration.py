"""0097: generalize reviewed media-script drafts into teacher AI material drafts."""
from __future__ import annotations

from teacher_app.maintenance.migrations import _add_columns, migration


@migration("0097-ai-material-drafts")
def ai_material_drafts_97(conn, kind: str) -> None:
    boolean = "BOOLEAN" if kind == "postgres" else "INTEGER"
    default_false = "FALSE" if kind == "postgres" else "0"
    _add_columns(
        conn,
        kind,
        "media_scripts",
        {
            "draft_type": "draft_type TEXT NOT NULL DEFAULT 'script'",
            "provider": "provider TEXT NOT NULL DEFAULT ''",
            "model": "model TEXT NOT NULL DEFAULT ''",
            "fallback_used": f"fallback_used {boolean} NOT NULL DEFAULT {default_false}",
            "publication_material_id": "publication_material_id TEXT NOT NULL DEFAULT ''",
        },
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_media_scripts_draft_type "
        "ON media_scripts(material_id,draft_type,status,updated_at)"
    )


__all__ = ["ai_material_drafts_97"]
