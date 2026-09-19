"""Legacy health adapter; canonical implementation lives in teacher_app."""
from __future__ import annotations

from release_contract import REQUIRED_MIGRATIONS
from teacher_app.maintenance import health as maintenance_health

app_version = maintenance_health.app_version
deployment_identity = maintenance_health.deployment_identity


def health_state(base=None):
    factory = getattr(base, "_db_conn", None) if base is not None else None
    return maintenance_health.health_state(factory)


def register_health(base):
    return maintenance_health.register_health(
        base.app,
        connection_factory=getattr(base, "_db_conn", None),
    )


__all__ = [
    "REQUIRED_MIGRATIONS",
    "app_version",
    "deployment_identity",
    "health_state",
    "register_health",
]
