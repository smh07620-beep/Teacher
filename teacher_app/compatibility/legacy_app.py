"""Load the 6.4 Flask app without replacing its routes."""

from __future__ import annotations


def load_legacy_app():
    """Return ``pgy_app.app`` — the current Render / run_web.sh entrypoint."""
    import pgy_app

    return pgy_app.app
