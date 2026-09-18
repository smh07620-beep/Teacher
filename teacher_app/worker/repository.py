"""Canonical persistence for the Web-side material worker protocol."""
from __future__ import annotations

import json
from typing import Any, Callable, Mapping

from teacher_app.common import db as common_db


def _write_heartbeat(
    conn,
    kind: str,
    *,
    worker_id: str,
    last_seen: str,
    capabilities_json: str,
    current_job_id: str,
) -> None:
    if kind == "postgres":
        conn.execute(
            "INSERT INTO material_worker_heartbeats"
            "(worker_id,last_seen,capabilities,current_job_id) "
            "VALUES(%s,%s,%s::jsonb,%s) "
            "ON CONFLICT(worker_id) DO UPDATE SET "
            "last_seen=EXCLUDED.last_seen,"
            "capabilities=EXCLUDED.capabilities,"
            "current_job_id=EXCLUDED.current_job_id",
            (worker_id, last_seen, capabilities_json, current_job_id),
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
            (worker_id, last_seen, capabilities_json, current_job_id),
        )


def upsert_heartbeat(
    worker_id: str,
    *,
    last_seen: str,
    capabilities: Mapping[str, Any],
    current_job_id: str = "",
    connection_factory: Callable[[], tuple[Any, str]] | None = None,
) -> None:
    """Persist one worker heartbeat through one canonical SQL owner.

    ``connection_factory`` is a temporary compatibility seam for legacy-host
    tests/adapters.  Normal canonical callers use ``teacher_app.common.db``.
    """
    raw = json.dumps(dict(capabilities), ensure_ascii=False)
    if connection_factory is not None:
        conn, kind = connection_factory()
        try:
            _write_heartbeat(
                conn,
                kind,
                worker_id=worker_id,
                last_seen=last_seen,
                capabilities_json=raw,
                current_job_id=current_job_id,
            )
        finally:
            conn.close()
        return

    with common_db.transaction() as (conn, kind):
        _write_heartbeat(
            conn,
            kind,
            worker_id=worker_id,
            last_seen=last_seen,
            capabilities_json=raw,
            current_job_id=current_job_id,
        )
