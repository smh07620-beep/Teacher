"""24-hour retention for temporary AI authoring data.

Kept forever (never touched here):
  * published PowerPoints / videos (status ``published`` or any publication row)
  * presentations that a kept (published) video was built from
  * approved lecture scripts (they are the disclosure record for AI narration)
  * course materials, atlas items and everything a learner can see

Removed once the *last activity* (``updated_at``) is older than the window:
  * unpublished PowerPoint / video artifacts, including approved-but-unpublished
  * unapproved lecture scripts and outline drafts that were never published
  * finished/failed script & outline jobs that no saved draft points to
  * private "authoring only" source materials that never joined a course

Every run writes one audit event with the counts.  Storage objects are deleted
strictly first and the database row is removed only afterwards, so a provider
failure leaves the row for the next hourly run instead of orphaning storage.
"""
from __future__ import annotations

import datetime as dt
import logging
import os
import shutil
import threading
from pathlib import Path
from typing import Any, Callable

from teacher_app.common import db as common_db
from teacher_app.storage import providers, r2_ledger
from teacher_app import storage as canonical_storage

LOGGER = logging.getLogger(__name__)

DEFAULT_RETENTION_HOURS = 24
_AUTHORING_DESC_PREFIXES = ("AI 講稿私人來源", "AI authoring source")


def retention_hours() -> int:
    try:
        value = int(os.environ.get("AI_TEMP_RETENTION_HOURS", str(DEFAULT_RETENTION_HOURS)))
    except (TypeError, ValueError):
        value = DEFAULT_RETENTION_HOURS
    return max(1, min(24 * 30, value))


def cutoff_iso(now: dt.datetime | None = None, hours: int | None = None) -> str:
    moment = now or dt.datetime.now(dt.timezone.utc)
    return (moment - dt.timedelta(hours=hours or retention_hours())).isoformat()


def _rows(sql: str, params: tuple = ()) -> list[dict]:
    with common_db.read_connection() as (conn, _kind):
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _execute(sql: str, params: tuple = ()) -> int:
    with common_db.transaction() as (conn, _kind):
        cursor = conn.execute(sql, params)
        return int(getattr(cursor, "rowcount", 0) or 0)


def _ph() -> str:
    with common_db.read_connection() as (_conn, kind):
        return common_db.placeholder(kind)


def _artifact_still_referenced(key: str, *, ignore_table: str, ignore_id: str) -> bool:
    """True when another row (kept or not) points at the same stored object."""
    if not key:
        return False
    ph = _ph()
    for table in ("ai_presentations", "ai_presentation_videos"):
        sql = f"SELECT id FROM {table} WHERE artifact_storage_key={ph}"
        params: tuple = (key,)
        if table == ignore_table:
            sql += f" AND id<>{ph}"
            params = (key, ignore_id)
        if _rows(sql + " LIMIT 1", params):
            return True
    return False


def _local_delete_factory(kind: str) -> Callable[[Any], None]:
    def delete(value) -> None:
        try:
            if kind == "video":
                from teacher_app.materials.ai_video_storage import VideoStorage

                root = VideoStorage()._local_root()
            else:
                from teacher_app.materials.ai_presentation_storage import PresentationStorage

                root = PresentationStorage()._local_root()
            target = (Path(root) / str(value)).resolve()
            if Path(root).resolve() in target.parents and target.exists():
                target.unlink()
                parent = target.parent
                if parent != Path(root).resolve() and not any(parent.iterdir()):
                    shutil.rmtree(parent, ignore_errors=True)
        except Exception:  # local dev only; never block the purge on it
            LOGGER.warning("retention: local artifact delete skipped", exc_info=True)

    return delete


def _delete_artifact(backend: str, key: str, *, kind: str, runtime) -> None:
    backend = str(backend or "").strip().lower()
    if not key or backend not in canonical_storage.VALID_BACKENDS:
        return
    adapters = runtime.delete_adapters(local_delete_object=_local_delete_factory(kind))
    canonical_storage.delete_strict(canonical_storage.DeleteRequest(backend, "object", key), adapters)
    if backend == "r2":
        try:
            r2_ledger.record_deleted(key)
        except Exception:
            LOGGER.warning("retention: R2 ledger update skipped", exc_info=True)


def _purge_videos(cutoff: str, runtime, summary: dict) -> None:
    ph = _ph()
    rows = _rows(
        "SELECT id,artifact_backend,artifact_storage_key FROM ai_presentation_videos "
        f"WHERE status<>{ph} AND updated_at<{ph} "
        "AND id NOT IN (SELECT video_id FROM ai_video_publications)",
        ("published", cutoff),
    )
    for row in rows:
        key = str(row.get("artifact_storage_key") or "")
        try:
            if not _artifact_still_referenced(key, ignore_table="ai_presentation_videos", ignore_id=row["id"]):
                _delete_artifact(row.get("artifact_backend"), key, kind="video", runtime=runtime)
            _execute(f"DELETE FROM ai_presentation_videos WHERE id={ph}", (row["id"],))
            summary["videos"] += 1
        except Exception:
            summary["errors"] += 1
            LOGGER.warning("retention: video %s not purged", row.get("id"), exc_info=True)


_PICTURE_PREFIX = "ai-presentations/images/"


def _picture_assets(slides_json: Any) -> set[tuple[str, str]]:
    """(backend, key) of every slide picture a deck's slides point at."""
    import json

    value = slides_json
    if isinstance(value, (str, bytes)):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return set()
    found: set[tuple[str, str]] = set()
    for slide in value if isinstance(value, list) else []:
        for block in (slide.get("blocks") or []) if isinstance(slide, dict) else []:
            asset = block.get("asset") if isinstance(block, dict) and block.get("type") == "image" else None
            if isinstance(asset, dict) and str(asset.get("key") or "").startswith(_PICTURE_PREFIX):
                found.add((str(asset.get("backend") or ""), str(asset["key"])))
    return found


def _picture_still_referenced(key: str) -> bool:
    ph = _ph()
    return bool(_rows(f"SELECT id FROM ai_presentations WHERE CAST(slides_json AS TEXT) LIKE {ph} LIMIT 1", (f"%{key}%",)))


def _purge_presentations(cutoff: str, runtime, summary: dict) -> None:
    ph = _ph()
    rows = _rows(
        "SELECT id,artifact_backend,artifact_storage_key,slides_json FROM ai_presentations "
        f"WHERE status<>{ph} AND updated_at<{ph} "
        "AND id NOT IN (SELECT presentation_id FROM ai_presentation_publications) "
        # a kept video was rendered from this deck: keep the deck's provenance
        "AND id NOT IN (SELECT presentation_id FROM ai_presentation_videos)",
        ("published", cutoff),
    )
    pictures: set[tuple[str, str]] = set()
    for row in rows:
        key = str(row.get("artifact_storage_key") or "")
        try:
            if not _artifact_still_referenced(key, ignore_table="ai_presentations", ignore_id=row["id"]):
                _delete_artifact(row.get("artifact_backend"), key, kind="presentation", runtime=runtime)
            _execute(f"DELETE FROM ai_presentations WHERE id={ph}", (row["id"],))
            pictures |= _picture_assets(row.get("slides_json"))
            summary["presentations"] += 1
        except Exception:
            summary["errors"] += 1
            LOGGER.warning("retention: presentation %s not purged", row.get("id"), exc_info=True)
    # Slide pictures are shared by content hash: remove one only when no
    # remaining deck (kept or not) still points at it.
    for backend, key in sorted(pictures):
        try:
            if not _picture_still_referenced(key):
                _delete_artifact(backend, key, kind="presentation", runtime=runtime)
        except Exception:
            summary["errors"] += 1
            LOGGER.warning("retention: slide picture not purged", exc_info=True)


def _purge_drafts_and_jobs(cutoff: str, summary: dict) -> None:
    ph = _ph()
    # Unapproved scripts / outlines that never became a material and no deck uses.
    summary["drafts"] += _execute(
        f"DELETE FROM media_scripts WHERE status<>{ph} AND updated_at<{ph} "
        "AND COALESCE(publication_material_id,'')='' "
        "AND id NOT IN (SELECT draft_id FROM ai_presentations)",
        ("approved", cutoff),
    )
    # Finished/failed jobs hold the raw AI text; drop them unless a saved row cites them.
    summary["jobs"] += _execute(
        f"DELETE FROM media_script_jobs WHERE status IN ({ph},{ph},{ph}) AND updated_at<{ph} "
        "AND id NOT IN (SELECT source_job_id FROM media_scripts WHERE COALESCE(source_job_id,'')<>'')",
        ("completed", "failed", "cancelled", cutoff),
    )


def _is_authoring_source(row: dict) -> bool:
    import json

    meta = row.get("storage_meta")
    if isinstance(meta, str):
        try:
            meta = json.loads(meta or "{}")
        except ValueError:
            meta = {}
    if isinstance(meta, dict) and meta.get("authoringOnly"):
        return True
    return str(row.get("description") or "").startswith(_AUTHORING_DESC_PREFIXES)


def _purge_private_sources(now: dt.datetime, hours: int, summary: dict, paths, runtime) -> None:
    from teacher_app.materials import service as material_service

    local_cutoff = (now.astimezone() - dt.timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M")
    ph = _ph()
    inactive = 0
    rows = _rows(
        "SELECT id,description,storage_meta FROM materials "
        f"WHERE COALESCE(course_id,'')='' AND date_added<{ph} AND active={ph}",
        (local_cutoff, inactive if _bool_is_int() else False),
    )
    for row in rows:
        if not _is_authoring_source(row):
            continue
        try:
            material_service.delete_material(str(row["id"]), paths=paths, storage_runtime=runtime)
            summary["sources"] += 1
        except Exception:
            summary["errors"] += 1
            LOGGER.warning("retention: private source %s not purged", row.get("id"), exc_info=True)


def _bool_is_int() -> bool:
    with common_db.read_connection() as (_conn, kind):
        return kind != "postgres"


def purge_expired(
    *,
    now: dt.datetime | None = None,
    hours: int | None = None,
    paths=None,
    storage_runtime=None,
) -> dict:
    """Run one purge pass and return the counts (also written to the audit log)."""
    moment = now or dt.datetime.now(dt.timezone.utc)
    window = hours or retention_hours()
    cutoff = cutoff_iso(moment, window)
    summary = {"videos": 0, "presentations": 0, "drafts": 0, "jobs": 0, "sources": 0, "errors": 0,
               "hours": window, "cutoff": cutoff}
    if paths is None:
        from teacher_app.config import storage_paths

        paths = storage_paths()
    runtime = storage_runtime
    if runtime is None:
        from teacher_app.storage.web_runtime import WebStorageRuntime

        runtime = WebStorageRuntime(paths)
    # Order matters: videos -> decks (decks keep rows a surviving video points at)
    # -> drafts/jobs -> private sources.
    _purge_videos(cutoff, runtime, summary)
    _purge_presentations(cutoff, runtime, summary)
    _purge_drafts_and_jobs(cutoff, summary)
    _purge_private_sources(moment, window, summary, paths, runtime)
    total = sum(summary[key] for key in ("videos", "presentations", "drafts", "jobs", "sources"))
    if total or summary["errors"]:
        try:
            from teacher_app.common import audit

            audit.record_event(
                actor={"username": "system:retention", "role": "system_admin"},
                action="retention.purge",
                target_type="ai_temp_data",
                target_id=cutoff,
                after={key: summary[key] for key in ("videos", "presentations", "drafts", "jobs", "sources", "errors", "hours")},
            )
        except Exception:
            LOGGER.warning("retention: audit event skipped", exc_info=True)
    LOGGER.info("retention purge: %s", summary)
    return summary


_started = threading.Event()


def start_background_purge(app, *, interval_seconds: int = 3600) -> bool:
    """Run ``purge_expired`` hourly inside the web process (idempotent, daemon)."""
    if _started.is_set() or str(os.environ.get("AI_TEMP_PURGE_ENABLED", "true")).strip().lower() in {"0", "false", "no", "off"}:
        return False
    if app.config.get("TESTING"):
        return False
    _started.set()

    def loop() -> None:
        stop = threading.Event()
        stop.wait(300)  # let the app finish booting before the first pass
        while not stop.is_set():
            try:
                with app.app_context():
                    purge_expired(paths=app.config.get("STORAGE_PATHS"))
            except Exception:
                LOGGER.warning("retention: purge pass failed", exc_info=True)
            stop.wait(interval_seconds)

    threading.Thread(target=loop, name="teacher-retention-purge", daemon=True).start()
    return True


__all__ = ["purge_expired", "start_background_purge", "retention_hours", "cutoff_iso"]
