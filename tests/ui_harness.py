"""Tiny deterministic HTTP harness for browser layout regressions.

It serves the repository's real static HTML/CSS/JS assets and only stubs the
read APIs needed to render representative learner/admin surfaces. It stays
stdlib-only so browser CI does not need production Python dependencies.
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
PORT = int(os.environ.get("TEACHER_UI_HARNESS_PORT", "4173"))

PORTAL_ASSETS = (
    "/home-profile-title-71.js",
    "/portal-navigation-73.js",
)
SYSTEM_ORDERED = (
    ("/shared-core.js", ("/api-client.js",)),
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
)
SYSTEM_ASSETS = (
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
)

SYSTEM_ADMIN = {
    "username": "ci-admin",
    "name": "CI 系統管理者",
    "role": "system_admin",
    "roles": ["system_admin"],
    "preferredGroup": "grpBio",
    "permissions": [
        "material.read", "course.view", "course.manage", "course.edit",
        "material.manage", "question.manage", "question.review", "exam.manage",
        "exam.publish", "result.group.read", "document.export",
        "education.cross_group.manage", "group.member.read", "group.content.manage",
        "group.result.read", "user.manage", "role.manage", "audit.read", "audit.view",
        "system.manage", "storage.manage", "backup.manage", "template.manage",
    ],
}


def _asset_tag(path: str) -> str:
    return f'<script defer src="{path}"></script>'


def _asset_present(html: str, path: str) -> bool:
    return bool(re.search(rf'(?:src|href)=["\']{re.escape(path)}(?:\?[^"\']*)?["\']', html))


def _append_missing(html: str, paths, closing_tag: str = "</body>") -> str:
    tags = [_asset_tag(path) for path in paths if not _asset_present(html, path)]
    if tags and closing_tag in html:
        html = html.replace(closing_tag, "\n".join(tags) + f"\n{closing_tag}", 1)
    return html


def _ensure_ordered_after(html: str, anchor_path: str, paths) -> str:
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
    return html[: anchor.end()] + insertion + html[anchor.end():]


def apply_assets(html: str, name: str) -> str:
    if name == "portal":
        return _append_missing(html, PORTAL_ASSETS)
    for anchor, paths in SYSTEM_ORDERED:
        html = _ensure_ordered_after(html, anchor, paths)
    return _append_missing(html, SYSTEM_ASSETS)


def json_bytes(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "TeacherUiHarness/1.0"

    def log_message(self, _format, *_args):
        return

    def send_payload(self, status: int, body: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, value, status: int = 200):
        self.send_payload(status, json_bytes(value), "application/json; charset=utf-8")

    def api_response(self, path: str):
        if path in {"/api/auth/me", "/api/auth/profile"}:
            return {"authenticated": True, "user": SYSTEM_ADMIN}
        if path == "/api/material-jobs":
            return {
                "jobs": [],
                "workers": [{
                    "workerId": "A8B5-TeacherWorker",
                    "status": "online",
                    "lastSeen": "2026-09-21T10:45:00+08:00",
                    "currentJobId": "",
                    "ffmpeg": True,
                    "libreOffice": True,
                    "workerVersion": "6.8.1",
                    "workerSha": "16f9064",
                    "workerBranch": "main",
                    "updateAvailable": False,
                    "lastUpdateCheckAt": "",
                }],
                "workerStatusAvailable": True,
                "workerStatusError": "",
                "pendingJobs": 0,
                "processingJobs": 0,
                "retryJobs": 0,
                "failedJobs": 0,
                "oldestPendingAt": "",
                "oldestPendingAgeSeconds": 0,
                "recentTerminalJobs": 0,
                "recentFailureRate": 0,
                "averageCompletedDurationSeconds": 0,
                "staging": {"backend": "r2", "available": True, "shared": True},
            }
        if path.startswith("/api/slides") or path.startswith("/api/courses") or path.startswith("/api/quiz-categories"):
            return []
        if path.startswith("/api/announcements"):
            return {"items": []}
        if path.startswith("/api/training-command-center"):
            return {"items": [], "todos": [], "courses": [], "progress": {}}
        if path.startswith("/api/dashboard/me"):
            return {"courses": [], "todos": [], "progress": 0}
        if path.startswith("/api/pgy/workflow/meta"):
            return {"groups": [], "assignments": [], "permissions": []}
        if path.startswith("/api/"):
            return {}
        return None

    def html_for(self, path: str) -> bytes | None:
        mapping = {
            "/": "index.html",
            "/internal": "area-internal.html",
            "/pgy": "area-pgy.html",
            "/system": "system.html",
            "/system.html": "system.html",
        }
        name = mapping.get(path)
        if not name:
            return None
        html = (STATIC / name).read_text(encoding="utf-8")
        html = apply_assets(html, "system" if path.startswith("/system") else "portal")
        return html.encode("utf-8")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        api = self.api_response(path)
        if api is not None:
            self.send_json(api)
            return
        html = self.html_for(path)
        if html is not None:
            self.send_payload(200, html, "text/html; charset=utf-8")
            return
        candidate = (STATIC / path.lstrip("/")).resolve()
        try:
            candidate.relative_to(STATIC.resolve())
        except ValueError:
            self.send_error(404)
            return
        if not candidate.is_file():
            self.send_error(404)
            return
        mime = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self.send_payload(200, candidate.read_bytes(), mime)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Teacher UI harness listening on http://127.0.0.1:{PORT}", flush=True)
    server.serve_forever()
