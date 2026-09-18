"""Compatibility module alias for canonical frontend asset registration."""
import sys

from teacher_app.frontend import assets as _assets


sys.modules[__name__] = _assets
