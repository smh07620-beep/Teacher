"""Run the real Teacher Flask factory for Playwright smoke coverage.

Unlike ``tests/ui_harness.py`` this process uses the canonical application
factory, real session/auth middleware, migrations, CSP and request hooks.  It
uses an isolated SQLite database and local temp storage only.
"""
from __future__ import annotations

import os
from pathlib import Path


PORT = int(os.environ.get("TEACHER_FLASK_UI_PORT", "4174"))
DB_PATH = Path(os.environ.get("TEACHER_FLASK_UI_DB", "/tmp/teacher-playwright-flask.sqlite"))
MATERIAL_STORAGE = Path(
    os.environ.get("TEACHER_FLASK_UI_STORAGE", "/tmp/teacher-playwright-materials")
)

# Apply deterministic local-only settings before importing Teacher modules.
os.environ.pop("DATABASE_URL", None)
os.environ["TEACHER_SQLITE_PATH"] = str(DB_PATH)
os.environ["MATERIAL_STORAGE"] = str(MATERIAL_STORAGE)
os.environ["SECRET_KEY"] = "teacher-playwright-real-flask-secret-0123456789"
os.environ["PRODUCTION_REQUIRE_SECRET"] = "false"
os.environ["SESSION_COOKIE_SECURE"] = "false"
os.environ["CSRF_ORIGIN_CHECK"] = "true"
os.environ["CSP_ENFORCE"] = "true"
os.environ["MATERIAL_BACKGROUND_JOBS"] = "true"
os.environ["MATERIAL_WORKER_ENABLED"] = "false"
os.environ["MATERIAL_DIRECT_UPLOAD_ENABLED"] = "false"
os.environ["MATERIAL_STORAGE_BACKEND"] = "local"

DB_PATH.parent.mkdir(parents=True, exist_ok=True)
MATERIAL_STORAGE.mkdir(parents=True, exist_ok=True)
DB_PATH.unlink(missing_ok=True)

from teacher_app.auth import accounts  # noqa: E402
from teacher_app.factory import create_app  # noqa: E402


app = create_app()
app.config.update(TESTING=False)

accounts.create_account(
    {
        "username": "ci-admin",
        "password": "ci-playwright-password",
        "name": "CI 系統管理者",
        "empId": "CI-ADMIN",
        "role": "system_admin",
        "roles": ["system_admin"],
        "preferredArea": "internal",
        "preferredGroup": "grpBio",
    }
)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT, threaded=True, use_reloader=False)
