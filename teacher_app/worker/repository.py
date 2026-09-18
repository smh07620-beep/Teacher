"""Canonical persistence for the Web-side material worker protocol."""
from __future__ import annotations

import json
from typing import Any, Mapping

from teacher_app.common import db as common_db


def upsert_heartbeat(
    worker_id: str,
    *,
    last_seen: str,
    capabilities: Mapping[str, Any],
    current_job_id: str = "",
) -> None:
    """Persist one worker heartbeat using the shared database seam."""
    raw = json.dumps(dict(capabilities), ensure_ascii=False)
    with common_db.transaction() as (conn, kind):
        if kind == "postgres":
            conn.execute(
                "INSERT INTO material_worker_heartbeats"
                "(worker_id,last_seen,capabilities,current_job_id) "
                "VALUES(%s,%s,%s::jsonb,%s) "
                "ON CONFLICT(worker_id) DO UPDATE SET "
                "last_seen=EXCLUDED.last_seen,"
                "capabilities=EXCLUDED.capabilities,"
                "current_job_id=EXCLUDED.current_job_id",
                (worker_id, last_seen, raw, current_job_id),
            )
        else:
            conn.execute(
                "INSERT INTO material_worker_heartbeats"
                "(worker_id,last_seen,capabilities,current_job_id) "
                "VALUES(?,?,?,?) "
                "ON CONFLICT(worker_id) DO UPDATE SET "
                "last_seen=excluded.last_seen,"
                "capabilities=excluded.capabilities,"
                "current_job_id=excluded.current_job_id",
                (worker_id, last_seen, raw, current_job_id),
            )
