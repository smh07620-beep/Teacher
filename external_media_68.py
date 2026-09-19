"""Compatibility module alias for canonical external-media routes."""
import sys
from teacher_app.materials import external_media_routes as _routes
sys.modules[__name__] = _routes
