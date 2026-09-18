"""Canonical production health state and route registration."""
from __future__ import annotations

import os
from typing import Callable

from flask import jsonify

from release_contract import RELEASE_VERSION, REQUIRED_MIGRATIONS
from teacher_app.common import db as common_db


def app_version() -> str:
    return RELEASE_VERSION or "unknown"


def deployment_identity() -> dict:
    """Return non-secret deploy identity for runtime verification."""
    raw_commit = str(os.environ.get("RENDER_GIT_COMMIT") or "").strip()
    branch = str(os.environ.get("RENDER_GIT_BRANCH") or "").strip()
    return {
        "provider": "render" if str(os.environ.get("RENDER") or "").lower() == "true" else "local",
        "branch": branch or None,
        "commit": raw_commit[:12] if raw_commit else None,
    }


def health_state(connection_factory: Callable | None = None):
    factory = connection_factory or common_db.get_connection
    database = {"ok": False, "kind": "unknown"}
    migrations = {
        "ok": False,
        "required": list(REQUIRED_MIGRATIONS),
        "applied": [],
        "missing": list(REQUIRED_MIGRATIONS),
    }
    conn = None
    try:
        conn, kind = factory()
        database = {"ok": True, "kind": str(kind or "unknown")}
        rows = conn.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
        applied = sorted({
            str(dict(row).get("version", ""))
            for row in rows
            if str(dict(row).get("version", "")).strip()
        })
        missing = [version for version in REQUIRED_MIGRATIONS if version not in applied]
        migrations = {
            "ok": not missing,
            "required": list(REQUIRED_MIGRATIONS),
            "applied": applied,
            "missing": missing,
        }
    except Exception:
        database = {"ok": False, "kind": "unavailable"}
        migrations = {
            "ok": False,
            "required": list(REQUIRED_MIGRATIONS),
            "applied": [],
            "missing": list(REQUIRED_MIGRATIONS),
        }
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    healthy = bool(database["ok"] and migrations["ok"])
    payload = {
        "ok": healthy,
        "status": "healthy" if healthy else "degraded",
        "version": app_version(),
        "deployment": deployment_identity(),
        "database": database,
        "migrations": migrations,
    }
    return payload, 200 if healthy else 503


def register_health(app, *, connection_factory: Callable | None = None):
    if app.extensions.get("teacher_health_65_registered"):
        return app

    def teacher_health():
        payload, status = health_state(connection_factory)
        return jsonify(payload), status

    existing = [
        rule
        for rule in app.url_map.iter_rules()
        if rule.rule == "/health" and "GET" in rule.methods
    ]
    if existing:
        for rule in existing:
            app.view_functions[rule.endpoint] = teacher_health
    else:
        app.add_url_rule(
            "/health",
            # Preserve the historical endpoint name as well as the URL.  This
            # lets the factory exclude the legacy rule instead of copying it
            # only to replace its view function later.
            endpoint="health",
            view_func=teacher_health,
            methods=["GET"],
        )
    app.extensions["teacher_health_65_registered"] = True
    return app


__all__ = ["app_version", "deployment_identity", "health_state", "register_health"]
