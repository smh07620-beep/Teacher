"""Legacy import adapter for canonical admin elevation behavior."""

from teacher_app.auth.elevation import (
    ELEVATION_ELIGIBLE_PERMISSIONS,
    TTL_SECONDS,
    now,
    register_admin_elevation_compat as register_admin_elevation,
)


__all__ = [
    "ELEVATION_ELIGIBLE_PERMISSIONS",
    "TTL_SECONDS",
    "now",
    "register_admin_elevation",
]
