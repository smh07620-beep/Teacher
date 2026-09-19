"""Legacy import adapter for canonical sensitive elevation behavior."""

from teacher_app.auth.elevation import (
    SENSITIVE_RULES,
    register_sensitive_elevation as register_sensitive_elevation_69,
    required_permissions as _required_permissions,
)


__all__ = ["SENSITIVE_RULES", "_required_permissions", "register_sensitive_elevation_69"]
