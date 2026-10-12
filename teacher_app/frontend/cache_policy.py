"""Canonical browser cache policy for the Teacher web shell."""
from __future__ import annotations

import re

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
# JS/CSS requested with ``?v=<this deploy's git commit>`` can never change under
# that URL (every deploy yields a new URL), so browsers may keep them for a year
# and skip the ~100 conditional requests a page otherwise makes on each visit.
IMMUTABLE_ASSET_CACHE_CONTROL = "public, max-age=31536000, immutable"
_COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")


def _is_current_commit_version(value: str) -> bool:
    """True only for a git-sha style ``v`` that equals this running deploy."""
    value = (value or "").strip().lower()
    if not _COMMIT_RE.match(value):
        return False
    from teacher_app.frontend.assets import _runtime_asset_version

    return value == _runtime_asset_version().lower()


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
        elif path.endswith((".css", ".js")):
            # Unversioned script/style URLs always revalidate (cheap 304) so fixes reach
            # users immediately. URLs carrying this deploy's commit are immutable.
            if response.status_code == 200 and _is_current_commit_version(request.args.get("v", "")):
                response.headers["Cache-Control"] = IMMUTABLE_ASSET_CACHE_CONTROL
            else:
                response.headers["Cache-Control"] = "no-cache"
        elif path.endswith((".png", ".jpg", ".jpeg", ".webp", ".svg")):
            response.headers["Cache-Control"] = "public, max-age=86400, stale-while-revalidate=604800"
        return response

    app.extensions["teacher_browser_cache_policy_registered"] = True
    return app


__all__ = ["PROTECTED_MEDIA_PREFIXES", "register_browser_cache_policy"]
