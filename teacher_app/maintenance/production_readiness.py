"""F6 production-readiness acceptance projection.

This is read-only. It aggregates existing canonical health, storage, worker,
email, and backup evidence without exposing credentials or creating synthetic
success states.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

from teacher_app.maintenance import backup as maintenance_backup
from teacher_app.maintenance import health
from teacher_app.notifications import delivery_health


def _check(key: str, label: str, ok: bool, detail: str = "", *, required: bool = True) -> dict:
    return {
        "key": key,
        "label": label,
        "ok": bool(ok),
        "required": bool(required),
        "detail": str(detail or "")[:500],
    }


def build_acceptance(
    *,
    material_runtime,
    connection_factory: Callable | None = None,
    backup_builder: Callable | None = None,
    email_builder: Callable | None = None,
) -> dict[str, Any]:
    ready_payload, _ready_status = health.ready_state(connection_factory)
    deployment = dict(ready_payload.get("deployment") or {})
    database = dict(ready_payload.get("database") or {})
    migrations = dict(ready_payload.get("migrations") or {})
    configuration = dict(ready_payload.get("configuration") or {})

    try:
        staging = dict(material_runtime.staging_capability() or {})
    except Exception as exc:
        staging = {"available": False, "shared": False, "backend": "", "error": type(exc).__name__}

    try:
        operations = dict(material_runtime.operations_status() or {})
    except Exception as exc:
        operations = {
            "workerStatusAvailable": False,
            "workers": [],
            "failedJobs": 0,
            "operationalIssues": [],
            "error": type(exc).__name__,
        }

    workers = list(operations.get("workers") or [])
    active_workers = [
        item for item in workers
        if str((item or {}).get("status") or "") in {"online", "busy"}
    ]
    worker_status_available = bool(operations.get("workerStatusAvailable", True))

    email_factory = email_builder or delivery_health.build_email_delivery_health
    try:
        email = dict(email_factory() or {})
        email_schedule = dict(email.get("schedule") or {})
        email_ok = str(email_schedule.get("health") or "healthy") == "healthy"
    except Exception as exc:
        email = {"error": type(exc).__name__}
        email_schedule = {}
        email_ok = False

    backup_factory = backup_builder or maintenance_backup.build_backup
    try:
        backup = dict(backup_factory(connection_factory) or {})
        backup_tables = dict(backup.get("tables") or {})
        backup_ok = bool(backup.get("sha256") and backup.get("format") == maintenance_backup.BACKUP_FORMAT)
        backup_summary = {
            "ok": backup_ok,
            "createdAt": str(backup.get("createdAt") or ""),
            "tableCount": len(backup_tables),
            "rowCount": sum(len(rows) for rows in backup_tables.values() if isinstance(rows, list)),
            "sha256Present": bool(backup.get("sha256")),
        }
    except Exception as exc:
        backup_ok = False
        backup_summary = {
            "ok": False,
            "tableCount": 0,
            "rowCount": 0,
            "sha256Present": False,
            "error": type(exc).__name__,
        }

    production = str(deployment.get("provider") or "") == "render"
    checks = [
        _check("web_ready", "Render Web readiness", bool(ready_payload.get("ok")), str(ready_payload.get("status") or "")),
        _check(
            "deployment_identity",
            "正式部署身份",
            (not production) or (
                str(deployment.get("branch") or "") == "main"
                and bool(deployment.get("commit"))
            ),
            f"{deployment.get('provider') or 'unknown'} / {deployment.get('branch') or 'unknown'} / {deployment.get('commit') or 'unknown'}",
        ),
        _check(
            "database",
            "Supabase / PostgreSQL",
            bool(database.get("ok")) and ((not production) or database.get("kind") == "postgres"),
            str(database.get("kind") or "unknown"),
        ),
        _check(
            "migrations",
            "Schema migrations",
            bool(migrations.get("ok")) and not list(migrations.get("missing") or []),
            f"missing={len(list(migrations.get('missing') or []))}",
        ),
        _check(
            "configuration",
            "正式環境設定",
            bool(configuration.get("ok")),
            "; ".join(str(item) for item in list(configuration.get("warnings") or [])[:5]),
        ),
        _check(
            "shared_storage",
            "Browser / Worker shared storage",
            bool(staging.get("available")) and bool(staging.get("shared")),
            str(staging.get("backend") or staging.get("error") or "unavailable"),
        ),
        _check(
            "worker",
            "院內 Worker",
            worker_status_available and bool(active_workers),
            f"online={len(active_workers)} / known={len(workers)}",
        ),
        _check(
            "email",
            "Email reminder delivery",
            email_ok,
            str(email_schedule.get("issue") or email_schedule.get("health") or "unknown"),
            required=False,
        ),
        _check(
            "backup",
            "Logical backup dry-run",
            backup_ok,
            f"tables={backup_summary.get('tableCount',0)} rows={backup_summary.get('rowCount',0)}",
        ),
    ]
    blockers = [item for item in checks if item["required"] and not item["ok"]]
    warnings = [item for item in checks if not item["required"] and not item["ok"]]
    return {
        "phase": "F6",
        "production": production,
        "ready": not blockers,
        "status": "production_ready" if not blockers else "blocked",
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "deployment": deployment,
        "storage": {
            "backend": str(staging.get("backend") or ""),
            "available": bool(staging.get("available")),
            "shared": bool(staging.get("shared")),
        },
        "worker": {
            "statusAvailable": worker_status_available,
            "active": len(active_workers),
            "known": len(workers),
            "failedJobs": int(operations.get("failedJobs") or 0),
            "pendingJobs": int(operations.get("pendingJobs") or 0),
            "processingJobs": int(operations.get("processingJobs") or 0),
        },
        "email": email,
        "backup": backup_summary,
    }


__all__ = ["build_acceptance"]
