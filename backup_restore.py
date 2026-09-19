"""Compatibility module alias for canonical maintenance backup routes."""
import sys

from teacher_app.maintenance import backup_routes as _routes


sys.modules[__name__] = _routes
