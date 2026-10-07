"""Canonical browser cache policy for the Teacher web shell."""
from __future__ import annotations

from flask import request

# Login-protected learning media. These must never be marked ``public`` and must
# not live for a day: a revised SOP/material keeps the same page URLs, so a long
# shared-cache lifetime would show learners the superseded pages.
PROTECTED_MEDIA_PREFIXES = (
    "/uploaded-slides/",
    "/material-preview/",
    "/question-images/",
    "/view/",
    "/download/",
)
PROTECTED_MEDIA_CACHE_CONTROL = "private, max-age=300"


def register_browser_cache_policy(app):
    if app.extensions.get("teacher_browser_cache_policy_registered"):
        return app

    @app.after_request
    def set_browser_cache_policy(response):
        """Keep repeat navigation fast without caching learner or admin data."""
        path = request.path.lower()
        if path.startswith("/api/") or path in {"/", "/internal", "/pgy", "/login", "/system"}:
            response.headers["Cache-Control"] = "no-store"
        elif path.startswith(PROTECTED_MEDIA_PREFIXES):
            # Only successful responses are briefly cacheable, and only by the
            # learner's own browser. Errors and redirects to signed URLs are not.
            ok = response.status_code == 200 or response.status_code == 206
            response.headers["Cache-Control"] = PROTECTED_MEDIA_CACHE_CONTROL if ok else "no-store"
        elif path.endswith((".css", ".js", ".png", ".jpg", ".jpeg", ".webp", ".svg")):
            response.headers["Cache-Control"] = "public, max-age=86400, stale-while-revalidate=604800"
        return response

    app.extensions["teacher_browser_cache_policy_registered"] = True
    return app


__all__ = ["PROTECTED_MEDIA_PREFIXES", "register_browser_cache_policy"]
