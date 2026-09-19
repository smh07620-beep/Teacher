"""Compatibility accessor for the canonical production WSGI application."""

from __future__ import annotations


def load_legacy_app():
    """Return ``pgy_app.app`` for historical callers using the old helper name."""
    import pgy_app

    return pgy_app.app
