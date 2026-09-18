"""Canonical browser cache policy for the Teacher web shell."""
from __future__ import annotations

from flask import request


def register_browser_cache_policy(app):
    if app.extensions.get("teacher_browser_cache_policy_registered"):
        return app

    @app.after_request
    def set_browser_cache_policy(response):
        """Keep repeat navigation fast without caching learner or admin data."""
        path = request.path.lower()
        if path.startswith("/api/") or path in {"/", "/internal", "/pgy", "/login", "/system"}:
            response.headers["Cache-Control"] = "no-store"
        elif path.endswith((".css", ".js", ".png", ".jpg", ".jpeg", ".webp", ".svg")):
            response.headers["Cache-Control"] = "public, max-age=86400, stale-while-revalidate=604800"
        return response

    app.extensions["teacher_browser_cache_policy_registered"] = True
    return app


__all__ = ["register_browser_cache_policy"]
