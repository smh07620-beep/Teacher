"""Canonical persistence for the Web-side material worker protocol.

This module owns worker queue/upload-session SQL only.  It deliberately does
not own schema DDL, HTTP routes, executor behavior, or storage adapters.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

from teacher_app.common import db as common_db


ConnectionFactory = Callable[[], tuple[Any, str]]

JOB_MUTABLE_FIELDS = {
    "status",
    "updated_at",
    "available_at",
    "started_at",
    "finished_at",
    "attempts",
    "max_attempts",
    "stage",
    "detail",
    "payload",
    "staging_path",
    "staging_backend",
    "staging_key",
    "original_name",
    "material_id",
    "source_sha256",
    "source_bytes",
    "error",
    "result",
    "worker_id",
    "worker_last_seen",
    "cancel_requested",
    "cleanup_pending",
}

UPLOAD_SESSION_MUTABLE_FIELDS = {
    "status",
    "updated_at",
    "r2_upload_id",
    "completed_parts",
    "payload",
}


def _json_decode(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return fallback
    return fallback


def _json_dump(value: Any, fallback: Any) -> str:
    if value is None:
        value = fallback
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def publish_receipt_row_to_dict(row: Any) -> dict[str, Any] | None:
    if not row:
        return None
    item = dict(row)
    item["result"] = _json_decode(item.get("result"), {})
    item["jobId"] = str(item.pop("job_id", "") or "")
    item["publishKey"] = str(item.pop("publish_key", "") or "")
    item["materialId"] = str(item.pop("material_id", "") or "")
    item["sourceSha256"] = str(item.pop("source_sha256", "") or "")
    item["workerId"] = str(item.pop("worker_id", "") or "")
    item["providerRef"] = str(item.pop("provider_ref", "") or "")
    item["createdAt"] = str(item.pop("created_at", "") or "")
    item["updatedAt"] = str(item.pop("updated_at", "") or "")
    item["publishedAt"] = str(item.pop("published_at", "") or "")
    return item


def get_publish_receipt(
    job_id: str,
    *,
    connection_factory: ConnectionFactory | None = None,
) -> dict[str, Any] | None:
    with _read_connection(connection_factory) as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT * FROM material_publish_receipts WHERE job_id={ph}",
            (job_id,),
        ).fetchone()
    return publish_receipt_row_to_dict(row)


def record_publish_receipt(
    *,
    job_id: str,
    publish_key: str,
    material_id: str,
    source_sha256: str,
    backend: str,
    worker_id: str,
    result: Mapping[str, Any],
    provider_ref: str,
    stamp: str,
    connection_factory: ConnectionFactory | None = None,
) -> tuple[dict[str, Any], bool]:
    """Insert or replay one provider-success receipt without changing identity."""

    expected = {
        "jobId": str(job_id),
        "publishKey": str(publish_key),
        "materialId": str(material_id),
        "sourceSha256": str(source_sha256).lower(),
        "backend": str(backend).lower(),
        "result": dict(result),
        "providerRef": str(provider_ref or ""),
    }
    with _transaction(connection_factory) as (conn, kind):
        ph = common_db.placeholder(kind)
        existing_row = conn.execute(
            f"SELECT * FROM material_publish_receipts WHERE job_id={ph} OR publish_key={ph}",
            (job_id, publish_key),
        ).fetchone()
        if existing_row:
            existing = publish_receipt_row_to_dict(existing_row) or {}
            for key in ("jobId", "publishKey", "materialId", "sourceSha256", "backend", "providerRef"):
                if str(existing.get(key) or "") != str(expected.get(key) or ""):
                    raise ValueError("provider publish receipt identity mismatch")
            if dict(existing.get("result") or {}) != expected["result"]:
                raise ValueError("provider publish receipt result mismatch")
            conn.execute(
                f"UPDATE material_publish_receipts SET worker_id={ph},updated_at={ph} WHERE job_id={ph}",
                (worker_id, stamp, job_id),
            )
            row = conn.execute(
                f"SELECT * FROM material_publish_receipts WHERE job_id={ph}",
                (job_id,),
            ).fetchone()
            return publish_receipt_row_to_dict(row) or {}, True

        result_mark = ph + ("::jsonb" if kind == "postgres" else "")
        conn.execute(
            "INSERT INTO material_publish_receipts "
            "(job_id,publish_key,material_id,source_sha256,backend,worker_id,result,provider_ref,status,created_at,updated_at,published_at) "
            f"VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{result_mark},{ph},'published',{ph},{ph},{ph})",
            (
                job_id,
                publish_key,
                material_id,
                source_sha256,
                backend,
                worker_id,
                _json_dump(dict(result), {}),
                provider_ref,
                stamp,
                stamp,
                stamp,
            ),
        )
        row = conn.execute(
            f"SELECT * FROM material_publish_receipts WHERE job_id={ph}",
            (job_id,),
        ).fetchone()
        decoded = publish_receipt_row_to_dict(row)
        if not decoded:
            raise RuntimeError("provider publish receipt insert did not persist")
        return decoded, False


@contextmanager
def _read_connection(
    connection_factory: ConnectionFactory | None = None,
) -> Iterator[tuple[Any, str]]:
    if connection_factory is None:
        with common_db.read_connection() as pair:
            yield pair
        return
    conn, kind = connection_factory()
    try:
        yield conn, kind
    finally:
        conn.close()


@contextmanager
def _transaction(
    connection_factory: ConnectionFactory | None = None,
) -> Iterator[tuple[Any, str]]:
    """Use the canonical transaction boundary, with a narrow test/adapter seam."""
    if connection_factory is None:
        with common_db.transaction() as pair:
            yield pair
        return

    conn, kind = connection_factory()
    try:
        if kind == "postgres":
            transaction = getattr(conn, "transaction", None)
            if callable(transaction):
                with transaction():
                    yield conn, kind
            else:
                yield conn, kind
            return

        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn, kind
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()
    finally:
        conn.close()


def material_job_row_to_dict(
    row: Any,
    *,
    include_payload: bool = False,
) -> dict[str, Any] | None:
    """Decode one material_jobs row into the established Web-facing shape."""
    if not row:
        return None
    item = dict(row)
    item["payload"] = _json_decode(item.get("payload"), {})
    item["result"] = _json_decode(item.get("result"), {})
    item["cancelRequested"] = bool(item.pop("cancel_requested", False))
    item["cleanupPending"] = bool(item.pop("cleanup_pending", False))
    item["createdAt"] = str(item.pop("created_at", "") or "")
    item["updatedAt"] = str(item.pop("updated_at", "") or "")
    item["availableAt"] = str(item.pop("available_at", "") or "")
    item["startedAt"] = str(item.pop("started_at", "") or "")
    item["finishedAt"] = str(item.pop("finished_at", "") or "")
    item["maxAttempts"] = int(item.pop("max_attempts", 3) or 3)
    item["materialId"] = str(item.pop("material_id", "") or "")
    item["sourceSha256"] = str(item.pop("source_sha256", "") or "")
    item["sourceBytes"] = int(item.pop("source_bytes", 0) or 0)
    item["workerId"] = str(item.pop("worker_id", "") or "")
    item["workerLastSeen"] = str(item.pop("worker_last_seen", "") or "")
    item["stagingBackend"] = str(item.pop("staging_backend", "local") or "local")
    item["stagingKey"] = str(item.pop("staging_key", "") or "")
    item["originalName"] = str(
        item.pop("original_name", "")
        or (item.get("payload") or {}).get("originalName")
        or ""
    )
    item["title"] = str((item.get("payload") or {}).get("title") or "")
    staging_path = str(item.pop("staging_path", "") or "")
    if include_payload:
        item["stagingPath"] = staging_path
    else:
        item.pop("payload", None)
    return item


def _job_db_value(kind: str, key: str, value: Any) -> tuple[str, Any]:
    ph = common_db.placeholder(kind)
    if key in {"payload", "result"}:
        return ph + ("::jsonb" if kind == "postgres" else ""), _json_dump(value, {})
    if key in {"cancel_requested", "cleanup_pending"}:
        return ph, bool(value) if kind == "postgres" else int(bool(value))
    return ph, value


def insert_material_job_on_connection(
    conn: Any,
    kind: str,
    job: Mapping[str, Any],
) -> None:
    columns = (
        "id",
        "status",
        "priority",
        "created_at",
        "updated_at",
        "available_at",
        "started_at",
        "finished_at",
        "attempts",
        "max_attempts",
        "stage",
        "detail",
        "payload",
        "staging_path",
        "staging_backend",
        "staging_key",
        "original_name",
        "material_id",
        "source_sha256",
        "source_bytes",
        "error",
        "result",
        "worker_id",
        "worker_last_seen",
        "cancel_requested",
        "cleanup_pending",
    )
    defaults: dict[str, Any] = {
        "status": "queued",
        "priority": 50,
        "started_at": "",
        "finished_at": "",
        "attempts": 0,
        "max_attempts": 3,
        "stage": "等待背景處理",
        "detail": "",
        "payload": {},
        "staging_path": "",
        "staging_backend": "local",
        "staging_key": "",
        "original_name": "",
        "material_id": "",
        "source_sha256": "",
        "source_bytes": 0,
        "error": "",
        "result": {},
        "worker_id": "",
        "worker_last_seen": "",
        "cancel_requested": False,
        "cleanup_pending": False,
    }
    marks: list[str] = []
    values: list[Any] = []
    for column in columns:
        value = job.get(column, defaults.get(column, ""))
        mark, value = _job_db_value(kind, column, value)
        marks.append(mark)
        values.append(value)
    conn.execute(
        f"INSERT INTO material_jobs ({','.join(columns)}) VALUES ({','.join(marks)})",
        tuple(values),
    )


def create_material_job(
    job: Mapping[str, Any],
    *,
    connection_factory: ConnectionFactory | None = None,
) -> dict[str, Any]:
    with _transaction(connection_factory) as (conn, kind):
        insert_material_job_on_connection(conn, kind, job)
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT * FROM material_jobs WHERE id={ph}",
            (str(job.get("id") or ""),),
        ).fetchone()
        decoded = material_job_row_to_dict(row, include_payload=True)
        if not decoded:
            raise RuntimeError("material job insert did not persist")
        return decoded


def get_material_job(
    job_id: str,
    *,
    include_payload: bool = False,
    connection_factory: ConnectionFactory | None = None,
) -> dict[str, Any] | None:
    with _read_connection(connection_factory) as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT * FROM material_jobs WHERE id={ph}",
            (job_id,),
        ).fetchone()
    return material_job_row_to_dict(row, include_payload=include_payload)


def list_material_jobs(
    limit: int = 30,
    *,
    connection_factory: ConnectionFactory | None = None,
) -> list[dict[str, Any]]:
    limit = max(1, min(100, int(limit or 30)))
    with _read_connection(connection_factory) as (conn, _kind):
        rows = conn.execute(
            f"SELECT * FROM material_jobs ORDER BY created_at DESC LIMIT {limit}"
        ).fetchall()
    return [
        material_job_row_to_dict(row, include_payload=False) or {}
        for row in rows
    ]


def _update_material_job_on_connection(
    conn: Any,
    kind: str,
    job_id: str,
    fields: Mapping[str, Any],
    *,
    expected_statuses: Sequence[str] = (),
    expected_worker_id: str | None = None,
    expected_updated_at: str | None = None,
) -> bool:
    clean = {key: value for key, value in fields.items() if key in JOB_MUTABLE_FIELDS}
    if not clean:
        return False
    ph = common_db.placeholder(kind)
    sets: list[str] = []
    values: list[Any] = []
    for key, value in clean.items():
        mark, value = _job_db_value(kind, key, value)
        sets.append(f"{key}={mark}")
        values.append(value)

    where = [f"id={ph}"]
    values.append(job_id)
    statuses = tuple(str(status) for status in expected_statuses if str(status))
    if statuses:
        marks = ",".join([ph] * len(statuses))
        where.append(f"status IN ({marks})")
        values.extend(statuses)
    if expected_worker_id is not None:
        where.append(f"worker_id={ph}")
        values.append(expected_worker_id)
    if expected_updated_at is not None:
        where.append(f"updated_at={ph}")
        values.append(expected_updated_at)

    cursor = conn.execute(
        f"UPDATE material_jobs SET {', '.join(sets)} WHERE {' AND '.join(where)}",
        tuple(values),
    )
    return int(getattr(cursor, "rowcount", 0) or 0) == 1


def update_material_job(
    job_id: str,
    *,
    fields: Mapping[str, Any],
    connection_factory: ConnectionFactory | None = None,
) -> dict[str, Any] | None:
    with _transaction(connection_factory) as (conn, kind):
        changed = _update_material_job_on_connection(conn, kind, job_id, fields)
        if not changed:
            return None
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT * FROM material_jobs WHERE id={ph}",
            (job_id,),
        ).fetchone()
        return material_job_row_to_dict(row, include_payload=True)


def cas_material_job(
    job_id: str,
    *,
    expected_statuses: Sequence[str],
    fields: Mapping[str, Any],
    expected_worker_id: str | None = None,
    expected_updated_at: str | None = None,
    connection_factory: ConnectionFactory | None = None,
) -> dict[str, Any] | None:
    """Compare-and-set one job and return the post-update row when won."""
    with _transaction(connection_factory) as (conn, kind):
        changed = _update_material_job_on_connection(
            conn,
            kind,
            job_id,
            fields,
            expected_statuses=expected_statuses,
            expected_worker_id=expected_worker_id,
            expected_updated_at=expected_updated_at,
        )
        if not changed:
            return None
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT * FROM material_jobs WHERE id={ph}",
            (job_id,),
        ).fetchone()
        return material_job_row_to_dict(row, include_payload=True)


def transition_owned_material_job(
    job_id: str,
    worker_id: str,
    *,
    from_statuses: Sequence[str] = ("processing",),
    fields: Mapping[str, Any],
    connection_factory: ConnectionFactory | None = None,
) -> dict[str, Any] | None:
    return cas_material_job(
        job_id,
        expected_statuses=from_statuses,
        expected_worker_id=worker_id,
        fields=fields,
        connection_factory=connection_factory,
    )


def touch_owned_material_job(
    job_id: str,
    worker_id: str,
    *,
    seen_at: str,
    connection_factory: ConnectionFactory | None = None,
) -> bool:
    return bool(
        transition_owned_material_job(
            job_id,
            worker_id,
            fields={"worker_last_seen": seen_at, "updated_at": seen_at},
            connection_factory=connection_factory,
        )
    )


def claim_next_material_job(
    worker_id: str,
    *,
    now: str,
    connection_factory: ConnectionFactory | None = None,
) -> dict[str, Any] | None:
    """Atomically claim at most one runnable job across PostgreSQL/SQLite."""
    with _transaction(connection_factory) as (conn, kind):
        if kind == "postgres":
            row = conn.execute(
                """
                SELECT * FROM material_jobs
                WHERE status IN ('queued','retry_wait')
                  AND cancel_requested=FALSE
                  AND available_at <= %s
                ORDER BY priority DESC, created_at ASC
                FOR UPDATE SKIP LOCKED LIMIT 1
                """,
                (now,),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT * FROM material_jobs
                WHERE status IN ('queued','retry_wait')
                  AND cancel_requested=0
                  AND available_at <= ?
                ORDER BY priority DESC, created_at ASC LIMIT 1
                """,
                (now,),
            ).fetchone()
        if not row:
            return None

        raw = dict(row)
        attempts = int(raw.get("attempts", 0) or 0) + 1
        changed = _update_material_job_on_connection(
            conn,
            kind,
            str(raw.get("id") or ""),
            {
                "status": "processing",
                "attempts": attempts,
                "started_at": now,
                "updated_at": now,
                "stage": "背景處理中",
                "detail": "Worker 已取得工作",
                "worker_id": worker_id,
            },
            expected_statuses=(str(raw.get("status") or ""),),
            expected_updated_at=str(raw.get("updated_at") or ""),
        )
        if not changed:
            return None
        ph = common_db.placeholder(kind)
        claimed = conn.execute(
            f"SELECT * FROM material_jobs WHERE id={ph}",
            (str(raw.get("id") or ""),),
        ).fetchone()
        return material_job_row_to_dict(claimed, include_payload=True)


def list_stale_processing_jobs(
    before: str,
    *,
    connection_factory: ConnectionFactory | None = None,
) -> list[dict[str, Any]]:
    with _read_connection(connection_factory) as (conn, kind):
        ph = common_db.placeholder(kind)
        rows = conn.execute(
            f"SELECT * FROM material_jobs WHERE status='processing' AND updated_at < {ph}",
            (before,),
        ).fetchall()
    return [
        material_job_row_to_dict(row, include_payload=True) or {}
        for row in rows
    ]


def list_cleanup_candidates(
    *,
    connection_factory: ConnectionFactory | None = None,
) -> list[dict[str, Any]]:
    with _read_connection(connection_factory) as (conn, _kind):
        rows = conn.execute(
            "SELECT * FROM material_jobs "
            "WHERE status IN ('completed','cancelled','failed')"
        ).fetchall()
    return [
        material_job_row_to_dict(row, include_payload=True) or {}
        for row in rows
    ]


def queue_aggregates(
    *,
    connection_factory: ConnectionFactory | None = None,
) -> dict[str, dict[str, Any]]:
    with _read_connection(connection_factory) as (conn, _kind):
        rows = conn.execute(
            "SELECT status, COUNT(*) AS count, MIN(created_at) AS oldest "
            "FROM material_jobs GROUP BY status"
        ).fetchall()
    return {
        str(dict(row).get("status") or ""): {
            "count": int(dict(row).get("count") or 0),
            "oldest": str(dict(row).get("oldest") or ""),
        }
        for row in rows
    }


def count_cleanup_pending_jobs(
    *,
    connection_factory: ConnectionFactory | None = None,
) -> int:
    with _read_connection(connection_factory) as (conn, kind):
        literal = "TRUE" if kind == "postgres" else "1"
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM material_jobs "
            f"WHERE cleanup_pending={literal}"
        ).fetchone()
    return int(dict(row).get("count") or 0) if row else 0


def _write_heartbeat(
    conn: Any,
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
    connection_factory: ConnectionFactory | None = None,
) -> None:
    """Persist one worker heartbeat through one canonical SQL owner."""
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


def list_heartbeats(
    limit: int = 50,
    *,
    connection_factory: ConnectionFactory | None = None,
) -> list[dict[str, Any]]:
    limit = max(1, min(200, int(limit or 50)))
    with _read_connection(connection_factory) as (conn, _kind):
        rows = conn.execute(
            "SELECT worker_id,last_seen,capabilities,current_job_id "
            f"FROM material_worker_heartbeats ORDER BY last_seen DESC LIMIT {limit}"
        ).fetchall()
    output = []
    for row in rows:
        item = dict(row)
        item["capabilities"] = _json_decode(item.get("capabilities"), {})
        output.append(item)
    return output


def upload_session_row_to_dict(row: Any) -> dict[str, Any] | None:
    if not row:
        return None
    item = dict(row)
    item["payload"] = _json_decode(item.get("payload"), {})
    item["completed_parts"] = _json_decode(item.get("completed_parts"), [])
    return item


def _upload_session_db_value(kind: str, key: str, value: Any) -> tuple[str, Any]:
    ph = common_db.placeholder(kind)
    if key in {"payload", "completed_parts"}:
        fallback = {} if key == "payload" else []
        return ph + ("::jsonb" if kind == "postgres" else ""), _json_dump(value, fallback)
    return ph, value


def insert_upload_session_on_connection(
    conn: Any,
    kind: str,
    session: Mapping[str, Any],
) -> None:
    columns = (
        "id",
        "job_id",
        "material_id",
        "staging_key",
        "original_name",
        "source_sha256",
        "source_bytes",
        "r2_upload_id",
        "part_size",
        "expected_parts",
        "payload",
        "completed_parts",
        "status",
        "created_at",
        "updated_at",
    )
    marks: list[str] = []
    values: list[Any] = []
    defaults = {"payload": {}, "completed_parts": [], "status": "uploading"}
    for column in columns:
        mark, value = _upload_session_db_value(
            kind,
            column,
            session.get(column, defaults.get(column, "")),
        )
        marks.append(mark)
        values.append(value)
    conn.execute(
        f"INSERT INTO material_upload_sessions ({','.join(columns)}) "
        f"VALUES ({','.join(marks)})",
        tuple(values),
    )


def create_upload_session(
    session: Mapping[str, Any],
    *,
    connection_factory: ConnectionFactory | None = None,
) -> dict[str, Any]:
    with _transaction(connection_factory) as (conn, kind):
        insert_upload_session_on_connection(conn, kind, session)
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT * FROM material_upload_sessions WHERE id={ph}",
            (str(session.get("id") or ""),),
        ).fetchone()
        decoded = upload_session_row_to_dict(row)
        if not decoded:
            raise RuntimeError("upload session insert did not persist")
        return decoded


def get_upload_session(
    upload_id: str,
    *,
    connection_factory: ConnectionFactory | None = None,
) -> dict[str, Any] | None:
    with _read_connection(connection_factory) as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT * FROM material_upload_sessions WHERE id={ph}",
            (upload_id,),
        ).fetchone()
    return upload_session_row_to_dict(row)


def _update_upload_session_on_connection(
    conn: Any,
    kind: str,
    upload_id: str,
    fields: Mapping[str, Any],
    *,
    expected_status: str | None = None,
) -> bool:
    clean = {
        key: value
        for key, value in fields.items()
        if key in UPLOAD_SESSION_MUTABLE_FIELDS
    }
    if not clean:
        return False
    ph = common_db.placeholder(kind)
    sets: list[str] = []
    values: list[Any] = []
    for key, value in clean.items():
        mark, value = _upload_session_db_value(kind, key, value)
        sets.append(f"{key}={mark}")
        values.append(value)
    where = [f"id={ph}"]
    values.append(upload_id)
    if expected_status is not None:
        where.append(f"status={ph}")
        values.append(expected_status)
    cursor = conn.execute(
        f"UPDATE material_upload_sessions SET {', '.join(sets)} "
        f"WHERE {' AND '.join(where)}",
        tuple(values),
    )
    return int(getattr(cursor, "rowcount", 0) or 0) == 1


def update_upload_session(
    upload_id: str,
    *,
    fields: Mapping[str, Any],
    connection_factory: ConnectionFactory | None = None,
) -> dict[str, Any] | None:
    with _transaction(connection_factory) as (conn, kind):
        if not _update_upload_session_on_connection(conn, kind, upload_id, fields):
            return None
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT * FROM material_upload_sessions WHERE id={ph}",
            (upload_id,),
        ).fetchone()
        return upload_session_row_to_dict(row)


def cas_upload_session_status(
    upload_id: str,
    *,
    expected_status: str,
    new_status: str,
    updated_at: str,
    fields: Mapping[str, Any] | None = None,
    connection_factory: ConnectionFactory | None = None,
) -> dict[str, Any] | None:
    changes = dict(fields or {})
    changes["status"] = new_status
    changes["updated_at"] = updated_at
    with _transaction(connection_factory) as (conn, kind):
        if not _update_upload_session_on_connection(
            conn,
            kind,
            upload_id,
            changes,
            expected_status=expected_status,
        ):
            return None
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT * FROM material_upload_sessions WHERE id={ph}",
            (upload_id,),
        ).fetchone()
        return upload_session_row_to_dict(row)


def list_stale_upload_sessions(
    before: str,
    *,
    connection_factory: ConnectionFactory | None = None,
) -> list[dict[str, Any]]:
    with _read_connection(connection_factory) as (conn, kind):
        ph = common_db.placeholder(kind)
        rows = conn.execute(
            f"SELECT * FROM material_upload_sessions "
            f"WHERE status='uploading' AND updated_at < {ph}",
            (before,),
        ).fetchall()
    return [upload_session_row_to_dict(row) or {} for row in rows]


def upload_session_status_counts(
    *,
    connection_factory: ConnectionFactory | None = None,
) -> dict[str, int]:
    with _read_connection(connection_factory) as (conn, _kind):
        rows = conn.execute(
            "SELECT status, COUNT(*) AS count "
            "FROM material_upload_sessions GROUP BY status"
        ).fetchall()
    return {
        str(dict(row).get("status") or ""): int(dict(row).get("count") or 0)
        for row in rows
    }


def finalize_upload_session_with_job(
    upload_id: str,
    *,
    completed_parts: Sequence[Mapping[str, Any]],
    updated_at: str,
    job: Mapping[str, Any],
    expected_status: str = "uploading",
    connection_factory: ConnectionFactory | None = None,
) -> dict[str, Any] | None:
    """Atomically mark one upload complete and create its single queue job.

    Storage completion/validation happens outside this transaction.  This unit
    only prevents a completed upload from creating zero or multiple jobs.
    """
    with _transaction(connection_factory) as (conn, kind):
        changed = _update_upload_session_on_connection(
            conn,
            kind,
            upload_id,
            {
                "status": "completed",
                "completed_parts": list(completed_parts),
                "updated_at": updated_at,
            },
            expected_status=expected_status,
        )
        if not changed:
            return None
        insert_material_job_on_connection(conn, kind, job)
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT * FROM material_jobs WHERE id={ph}",
            (str(job.get("id") or ""),),
        ).fetchone()
        return material_job_row_to_dict(row, include_payload=True)
