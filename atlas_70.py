"""Compatibility module alias for canonical Atlas routes."""
import sys
from teacher_app.atlas import routes as _routes
sys.modules[__name__] = _routes
