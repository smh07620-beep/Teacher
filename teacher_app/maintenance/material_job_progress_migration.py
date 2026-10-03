"""Persist Worker-reported material processing progress."""
from teacher_app.maintenance.migrations import _add_columns, migration


@migration("0107-material-job-progress")
def material_job_progress_107(conn, kind: str) -> None:
    _add_columns(
        conn,
        kind,
        "material_jobs",
        {
            "progress_percent": "progress_percent INTEGER NOT NULL DEFAULT 0",
        },
    )


__all__ = ["material_job_progress_107"]
