"""Inject Teacher workflow/security/maintenance/workspace assets into UI pages."""

import os
import re
from pathlib import Path


ASSET_MANIFEST = {
    "portal": {
        "body": (
            "/home-profile-title-71.js",
            "/portal-navigation-73.js",
        ),
    },
    "system": {
        "ordered": (
            (
                "/shared-core.js",
                (
                    "/api-client.js",
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
        "head": (),
        "body": (
            "/system-csp-actions.js",
            "/pgy-workflow.js",
            "/roles-signing-66.js",
            "/maintenance-64.js",
            "/workspace-shell-70.js",
            "/training-command-center-71.js",
            "/pgy-competency-matrix-71.js",
            "/learning-analytics-71.js",
            "/notification-center-71.js",
            "/worker-status-70.js",
            "/admin-results.js",
            "/admin-course-material.js",
            "/admin-people.js",
            "/admin-announcements.js",
            "/admin-system.js",
            "/admin-materials.js",
            "/admin-question-bank.js",
            "/admin-quiz-materials.js",
            "/admin-question-editor-ui.js",
            "/admin-question-actions.js",
            "/review-links-66.js",
            "/admin-jobs.js",
            "/admin-material-upload.js",
            "/material-upload-client.js",
            "/admin-ai-questions.js",
            "/admin-question-panel.js",
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
    """Place one canonical copy of each script directly after its anchor."""
    for path in paths:
        pattern = re.compile(
            rf'\s*<script\b[^>]*\bsrc=["\']{re.escape(path)}(?:\?[^"\']*)?["\'][^>]*></script>',
            re.IGNORECASE,
        )
        html = pattern.sub("", html)
    anchor = re.search(
        rf'<script\b[^>]*\bsrc=["\']{re.escape(anchor_path)}(?:\?[^"\']*)?["\'][^>]*></script>',
        html,
        re.IGNORECASE,
    )
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
        value = Path(__file__).with_name("VERSION").read_text(encoding="utf-8").strip()
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

            # Teacher 7.2/7.3 portal presentation is intentionally one-shot:
            # identity and navigation can enhance public learning pages without
            # adding another MutationObserver or changing authorization.
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
            return response
        return response

    return app
