"""Teacher 6.5 production health endpoint.

The health response exposes only operational state.  It never returns
database URLs, credentials, API keys, stack traces, or exception details.
"""
from __future__ import annotations

import os
from pathlib import Path

from flask import jsonify


REQUIRED_MIGRATIONS = (
    "0064-baseline",
    "0065-architecture",
    "0066-additive-rbac-pgy-signing",
    "0067-smart-learning-content",
    "0067-render-worker-shared-staging",
    "0067-b-free-local-worker",
    "0068-external-interactive-media",
    "0069-user-profile-titles",
    "0072-course-bundle-idempotency",
    "0073-course-bundle-followups",
)


def app_version() -> str:
    try:
        value = (
            Path(__file__)
            .with_name("VERSION")
            .read_text(encoding="utf-8")
            .strip()
        )
        return value or "unknown"
    except Exception:
        return "unknown"


def deployment_identity() -> dict:
    """Return non-secret deploy identity for runtime verification."""
    raw_commit = str(os.environ.get("RENDER_GIT_COMMIT") or "").strip()
    branch = str(os.environ.get("RENDER_GIT_BRANCH") or "").strip()
    return {
        "provider": "render" if str(os.environ.get("RENDER") or "").lower() == "true" else "local",
        "branch": branch or None,
        "commit": raw_commit[:12] if raw_commit else None,
    }

def health_state(base):
    database = {
        "ok": False,
        "kind": "unknown",
    }

    migrations = {
        "ok": False,
        "required": list(REQUIRED_MIGRATIONS),
        "applied": [],
        "missing": list(REQUIRED_MIGRATIONS),
    }

    conn = None

    try:
        conn, kind = base._db_conn()

        database = {
            "ok": True,
            "kind": str(kind or "unknown"),
        }

        rows = conn.execute(
            """
            SELECT version
            FROM schema_migrations
            ORDER BY version
            """
        ).fetchall()

        applied = sorted(
            {
                str(dict(row).get("version", ""))
                for row in rows
                if str(
                    dict(row).get(
                        "version",
                        "",
                    )
                ).strip()
            }
        )

        missing = [
            version
            for version in REQUIRED_MIGRATIONS
            if version not in applied
        ]

        migrations = {
            "ok": not missing,
            "required": list(
                REQUIRED_MIGRATIONS
            ),
            "applied": applied,
            "missing": missing,
        }

    except Exception:
        # Deliberately suppress exception text.  Database URLs and
        # driver exceptions can contain credentials or infrastructure
        # details that must never appear in a public health response.
        database = {
            "ok": False,
            "kind": "unavailable",
        }

        migrations = {
            "ok": False,
            "required": list(
                REQUIRED_MIGRATIONS
            ),
            "applied": [],
            "missing": list(
                REQUIRED_MIGRATIONS
            ),
        }

    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    healthy = bool(
        database["ok"]
        and migrations["ok"]
    )

    payload = {
        "ok": healthy,
        "status": (
            "healthy"
            if healthy
            else "degraded"
        ),
        "version": app_version(),
        "deployment": deployment_identity(),
        "database": database,
        "migrations": migrations,
    }

    return payload, 200 if healthy else 503


def register_health(base):
    app = base.app

    if app.extensions.get(
        "teacher_health_65_registered"
    ):
        return app

    def teacher_health():
        payload, status = health_state(
            base
        )
        return jsonify(payload), status

    # Render already probes /health.  If the legacy application has an
    # older /health route, replace its view function instead of adding a
    # competing URL rule.
    existing = [
        rule
        for rule in app.url_map.iter_rules()
        if rule.rule == "/health"
        and "GET" in rule.methods
    ]

    if existing:
        for rule in existing:
            app.view_functions[
                rule.endpoint
            ] = teacher_health
    else:
        app.add_url_rule(
            "/health",
            endpoint="teacher_health_65",
            view_func=teacher_health,
            methods=["GET"],
        )

    app.extensions[
        "teacher_health_65_registered"
    ] = True

    return app
