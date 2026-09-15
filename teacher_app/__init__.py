"""Teacher 6.5 application package.

This package is the incremental modular architecture. Legacy ``app.py`` and
``pgy_app:app`` remain the production entrypoints until later milestones
switch Render over after the full test suite is green.
"""

from teacher_app.factory import create_app

__all__ = ["create_app"]
