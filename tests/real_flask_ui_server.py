"""Launch the real canonical Flask composition for browser CI smoke tests.

This is intentionally separate from ``ui_harness.py``: the deterministic
harness owns broad responsive layout coverage, while this process proves that
``teacher_app.factory.create_app()`` still serves the real pages, security
headers, migrations and runtime asset injection together.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


PORT = int(os.environ.get("TEACHER_REAL_FLASK_PORT", "4174"))
STATE_DIR = Path(tempfile.mkdtemp(prefix="teacher-real-flask-ci-"))

# Force an isolated SQLite runtime regardless of the caller's shell. PostgreSQL
# compatibility is exercised independently by the dedicated CI service job.
os.environ.pop("DATABASE_URL", None)
os.environ["TEACHER_SQLITE_PATH"] = str(STATE_DIR / "teacher-ci.db")
os.environ["MATERIAL_STORAGE"] = str(STATE_DIR / "materials")
os.environ["SECRET_KEY"] = "teacher-playwright-ci-secret-key-1234567890"
os.environ["PRODUCTION_REQUIRE_SECRET"] = "false"
os.environ["SESSION_COOKIE_SECURE"] = "false"
os.environ["CSRF_ORIGIN_CHECK"] = "false"
os.environ["CSP_ENFORCE"] = "true"
os.environ["MATERIAL_BACKGROUND_JOBS"] = "false"
os.environ["MATERIAL_WORKER_ENABLED"] = "false"
os.environ["AI_EXTERNAL_PROCESSING_ENABLED"] = "false"
os.environ["ASSET_VERSION"] = "playwright-real-flask"

from teacher_app import create_app  # noqa: E402


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)
