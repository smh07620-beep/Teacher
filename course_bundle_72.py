"""Compatibility module alias for canonical Course Wizard bundle routes."""
import sys
from teacher_app.courses import bundle_routes as _routes
sys.modules[__name__] = _routes
