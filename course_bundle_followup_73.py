"""Compatibility module alias for canonical Course Wizard follow-up routes."""
import sys
from teacher_app.courses import bundle_followup_routes as _routes
sys.modules[__name__] = _routes
