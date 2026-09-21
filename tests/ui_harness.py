"""Tiny deterministic HTTP harness for browser layout regressions.

It serves the repository's real static HTML/CSS/JS assets and only stubs the
read APIs needed to render representative learner/admin surfaces.  It does not
start the production Flask app or require secrets/database access.
"""
from __future__ import annotations

import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from teacher_app.frontend.assets import _apply_asset_manifest


ROOT = Path(__file__).parents[1]
STATIC = ROOT / "static"
PORT = int(os.environ.get("TEACHER_UI_HARNESS_PORT", "4173"))

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
                "workers": [
                    {
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
                    }
                ],
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
        if path in {"/", "/internal", "/pgy"}:
            html = _apply_asset_manifest(html, "portal")
        elif path in {"/system", "/system.html"}:
            html = _apply_asset_manifest(html, "system")
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
        relative = path.lstrip("/")
        candidate = (STATIC / relative).resolve()
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
