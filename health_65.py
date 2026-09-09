"""Teacher 6.5 production health endpoint.

The health response exposes only operational state.  It never returns
database URLs, credentials, API keys, stack traces, or exception details.
"""
from __future__ import annotations

from pathlib import Path

from flask import jsonify


REQUIRED_MIGRATIONS = (
    "0064-baseline",
    "0065-architecture",
    "0066-additive-rbac-pgy-signing",
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
