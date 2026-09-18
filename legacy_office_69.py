"""Compatibility module alias for canonical Office download safety routes."""
import sys

from teacher_app.materials import legacy_office as _routes


sys.modules[__name__] = _routes
