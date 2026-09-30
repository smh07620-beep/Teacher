"""0102: persisted, allow-listed provenance for AI PowerPoint revisions."""
from __future__ import annotations

from teacher_app.maintenance.migrations import _add_columns, migration


@migration("0102-ai-presentation-provenance")
def ai_presentation_provenance_102(conn, kind: str) -> None:
    """Persist a safe RAG/provenance snapshot beside every PPT revision."""
    payload = "JSONB" if kind == "postgres" else "TEXT"
    payload_default = "'{}'::jsonb" if kind == "postgres" else "'{}'"
    _add_columns(
        conn,
        kind,
        "ai_presentations",
        {"provenance_json": f"provenance_json {payload} NOT NULL DEFAULT {payload_default}"},
    )


__all__ = ["ai_presentation_provenance_102"]
