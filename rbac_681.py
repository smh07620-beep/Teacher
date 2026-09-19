"""Compatibility module alias for canonical RBAC route registration."""
import sys

from teacher_app.auth import rbac_routes as _routes


sys.modules[__name__] = _routes
