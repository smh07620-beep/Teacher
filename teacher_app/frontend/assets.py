"""Inject Teacher workflow/security/maintenance/workspace assets into UI pages."""

import logging
import os
import re
from pathlib import Path


LOGGER = logging.getLogger(__name__)

# Compatibility-only static paths are deliberately served but never injected
# into current pages. They keep already-open/stale browser tabs from turning a
# removed asset request into a 404 during a rolling deployment.
LEGACY_COMPAT_ASSETS = (
    "/admin-entrypoint-69.js",
)

ASSET_MANIFEST = {
    "portal": {
        # Back-office destination table; portal links ask it for their URLs.
        "ordered": (
            ("/shared-core.js", ("/workspace-routes-1007.js",)),
        ),
        "body": (
            "/home-profile-title-71.js",
            "/portal-navigation-73.js",
            "/learner-todo-convergence-1025.js",
            "/learning-progress-convergence-1025.js",
        ),
    },
    "system": {
        "ordered": (
            (
                "/shared-core.js",
                (
                    # Back-office destination table (names, aliases, areas,
                    # URLs). Read by the workspace shell and every script that
                    # links to a workspace, so it must come first.
                    "/workspace-routes-1007.js",
                    # RBAC publishes the readiness promise consumed by every
                    # teacher workspace. Load it before the large deferred
                    # admin bundle so first navigation cannot race it in CI.
                    "/rbac-ui-681.js",
                    "/api-client.js",
                    # Middleware that shares identical read-only API calls made
                    # by many page scripts; must follow api-client.js and
                    # precede every feature script that fetches at load.
                    "/api-get-dedupe-1007.js",
                ),
            ),
            (
                "/system-admin.js",
                (
                    "/admin-workspace.js",
                    "/admin-results-data.js",
                    "/admin-results-workspace.js",
                    "/admin-exam-settings.js",
                    "/admin-doc-templates.js",
                    "/admin-pgy-assessments.js",
                ),
            ),
        ),
        "head": (
            "/teacher-workspace-1014.css",
        ),
        "body": (
            "/system-csp-actions.js",
            "/pgy-workflow.js",
            "/roles-signing-66.js",
            "/maintenance-64.js",
            "/workspace-shell-70.js",
            "/teacher-workspace-1014.js",
            "/teacher-workspace-nav-fix-1014.js",
            "/teacher-media-script-1014.js",
            "/teacher-media-source-fix-1014.js",
            "/teacher-voice-catalog-1026.js",
            "/teacher-media-audio-1014.js",
            "/teacher-media-subtitle-1014.js",
            "/teacher-ai-presentation-1016.js",
            "/teacher-ai-presentation-editor-f5.js",
            "/teacher-ai-presentation-video-handoff-f5.js",
            "/teacher-ai-video-1015.js",
            "/teacher-media-mvp-status-1014.js",
            "/teacher-media-status-fix-1014.js",
            "/teacher-media-help-1014.js",
            "/teacher-media-free-tts-1014.js",
            "/teacher-paper-template-manager-1014.js",
            "/training-command-center-71.js",
            "/pgy-competency-matrix-71.js",
            "/learning-analytics-71.js",
            "/learning-progress-convergence-1025.js",
            "/notification-center-71.js",
            "/worker-status-70.js",
            "/production-readiness-f6.js",
            "/worker-status-convergence-101.js",
            "/system-admin-focus-1014.js",
            "/admin-results.js",
            "/admin-course-material.js",
            "/admin-compliance-91.js",
            "/admin-people.js",
            "/admin-announcements.js",
            "/admin-system.js",
            "/admin-competency-matrix-92.js",
            "/training-intervention-f3.js",
            "/admin-materials.js",
            "/admin-question-bank.js",
            "/course-wizard-group-fix-1014.js",
            "/admin-quiz-materials.js",
            "/admin-question-editor-ui.js",
            "/admin-question-actions.js",
            "/review-links-66.js",
            "/admin-jobs.js",
            "/admin-material-upload.js",
            "/material-upload-client.js",
            "/teacher-ai-material-1014.js",
            "/teacher-ai-material-convergence-1014.js",
            "/teacher-media-recorder-1014.js",
            "/admin-ai-questions.js",
            "/admin-question-panel.js",
            "/content-audience-1014.js",
            "/learner-content-audience-1014.js",
            "/admin-external-media.js",
            "/admin-results-export.js",
            "/learner-exam-controls.js",
            "/learner-result-chart.js",
            "/teacher-content-studio-71.js",
            "/teacher-content-tool-panels-710.js",
            "/teacher-content-latency-712.js",
            "/teacher-content-composer-72.js",
            "/teacher-ux-convergence-72.js",
            "/learner-ui-cleanup-71.js",
            "/portal-navigation-73.js",
            "/teacher-ui-resilience-1014.js",
            "/course-wizard-runtime-fix-1014.js",
            "/teacher-interface-convergence-1014.js",
            "/teacher-authoring-source-fix-1017.js",
            "/teacher-ai-media-studio-1018.js",
            "/teacher-ai-media-controls-1023.js",
            "/teacher-assignment-experience-1014.js",
            "/teacher-persona-isolation-1014.js",
            "/product-convergence-101.js",
            "/teacher-action-queue-1024.js",
            "/teacher-assessment-inline-1031.js",
            "/teacher-learners-p2.js",
            "/learner-reading-progress-f2.js",
            "/learner-narration-1100.js",
            "/course-lifecycle-f2.js",
            "/teacher-course-tracking-f2.js",
            "/learner-study-exam-loop-1032.js",
        ),
    },
}


def _asset_tag(path: str) -> str:
    if path.endswith(".css"):
        return f'<link rel="stylesheet" href="{path}">'
    return f'<script defer src="{path}"></script>'


def _asset_present(html: str, path: str) -> bool:
    return bool(re.search(rf'(?:src|href)=["\']{re.escape(path)}(?:\?[^"\']*)?["\']', html))


def _append_missing_assets(html: str, paths, closing_tag: str) -> str:
    tags = [_asset_tag(path) for path in paths if not _asset_present(html, path)]
    if tags and closing_tag in html:
        html = html.replace(closing_tag, "\n".join(tags) + f"\n{closing_tag}", 1)
    return html


def _ensure_ordered_scripts_after(html: str, anchor_path: str, paths) -> str:
    """Place one canonical copy of each script directly after its anchor.

    Fail closed on a missing anchor: never remove existing scripts unless the
    anchor that will receive their canonical copies is present.
    """
    anchor_pattern = re.compile(
        rf'<script\b[^>]*\bsrc=["\']{re.escape(anchor_path)}(?:\?[^"\']*)?["\'][^>]*></script>',
        re.IGNORECASE,
    )
    if not anchor_pattern.search(html):
        return html

    for path in paths:
        pattern = re.compile(
            rf'\s*<script\b[^>]*\bsrc=["\']{re.escape(path)}(?:\?[^"\']*)?["\'][^>]*></script>',
            re.IGNORECASE,
        )
        html = pattern.sub("", html)

    # Re-resolve after removals because deleting a script before the anchor
    # changes its character offsets.
    anchor = anchor_pattern.search(html)
    if not anchor:
        return html
    insertion = "\n" + "\n".join(_asset_tag(path) for path in paths)
    return html[: anchor.end()] + insertion + html[anchor.end() :]


def _apply_asset_manifest(html: str, name: str) -> str:
    manifest = ASSET_MANIFEST[name]
    for anchor_path, paths in manifest.get("ordered", ()):
        html = _ensure_ordered_scripts_after(html, anchor_path, paths)
    html = _append_missing_assets(html, manifest.get("head", ()), "</head>")
    html = _append_missing_assets(html, manifest.get("body", ()), "</body>")
    return html


def _runtime_asset_version() -> str:
    raw = str(os.environ.get("ASSET_VERSION") or os.environ.get("RENDER_GIT_COMMIT") or "").strip()
    if raw:
        return re.sub(r"[^A-Za-z0-9._-]", "", raw)[:12] or "runtime"
    try:
        value = Path(__file__).resolve().parents[2].joinpath("VERSION").read_text(encoding="utf-8").strip()
        return re.sub(r"[^A-Za-z0-9._-]", "", value) or "runtime"
    except Exception:
        return "runtime"


def _rewrite_local_asset_versions(html: str) -> str:
    """Bind same-origin JS/CSS cache keys to the deployed build identity."""
    version = _runtime_asset_version()
    pattern = re.compile(r'(?P<prefix>(?:src|href)="/[^"]+?\.(?:js|css))(?:\?v=[^"]*)?"')
    return pattern.sub(lambda match: f'{match.group("prefix")}?v={version}"', html)


def register_pgy_frontend(app):
    if app.extensions.get("pgy_frontend_registered"):
        return app
    app.extensions["pgy_frontend_registered"] = True

    @app.after_request
    def inject_pgy_workflow_assets(response):
        path = ""
        try:
            if response.status_code != 200:
                return response
            if not str(response.content_type or "").startswith("text/html"):
                return response
            try:
                from flask import request
                path = request.path
            except Exception:
                return response
            if response.direct_passthrough:
                response.direct_passthrough = False

            if path in {"/", "/internal", "/pgy"}:
                html = response.get_data(as_text=True)
                html = _apply_asset_manifest(html, "portal")
                html = _rewrite_local_asset_versions(html)
                response.set_data(html)
                response.content_length = len(response.get_data())
                return response

            if path not in {"/system", "/system.html"}:
                return response

            html = response.get_data(as_text=True)
            html = _apply_asset_manifest(html, "system")
            html = _rewrite_local_asset_versions(html)
            response.set_data(html)
            response.content_length = len(response.get_data())
        except Exception:
            LOGGER.exception(
                "Teacher frontend asset injection failed path=%s",
                path or "<unknown>",
            )
        return response

    return app
