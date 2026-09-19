"""Compatibility module alias for canonical question-bank routes."""
import sys
from teacher_app.assessments import question_bank_routes as _routes
sys.modules[__name__] = _routes
