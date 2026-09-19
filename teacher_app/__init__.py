"""Canonical Teacher application package.

``teacher_app.factory.create_app`` is the production composition root and
``pgy_app:app`` is its thin WSGI entrypoint. Root ``app.py`` remains an import
compatibility alias only.
"""

from teacher_app.factory import create_app

__all__ = ["create_app"]
