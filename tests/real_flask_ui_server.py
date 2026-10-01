"""Launch the real canonical Flask composition for browser CI smoke tests.

This is intentionally separate from ``ui_harness.py``: the deterministic
harness owns broad responsive layout coverage, while this process proves that
``teacher_app.factory.create_app()`` still serves the real pages, security
headers, migrations and runtime asset injection together.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
os.environ["ASSET_VERSION"] = "realflaskci"

from teacher_app import create_app  # noqa: E402
from teacher_app.auth import accounts, elevation, repository as auth_repository  # noqa: E402


app = create_app()


def _seed_browser_account(payload: dict) -> None:
    """Create deterministic browser-only fixtures through canonical account rules."""
    if auth_repository.find_user(payload["username"]):
        return
    accounts.create_account(payload)


_fixture_password = str(os.environ.get("TEACHER_CI_BROWSER_PASSWORD") or "").strip()
if _fixture_password:
    _seed_browser_account(
        {
            "username": "gp08admin",
            "password": _fixture_password,
            "name": "GP08 系統管理者",
            "empId": "GP0800",
            "role": "system_admin",
            "roles": ["system_admin"],
            "preferredArea": "internal",
            "preferredGroup": "grpBio",
        }
    )
    _seed_browser_account(
        {
            "username": "gp07dual",
            "password": _fixture_password,
            "name": "GP07 雙角色",
            "empId": "GP0701",
            "role": "student",
            "roles": ["student", "clinical_teacher"],
            "preferredArea": "internal",
            "preferredGroup": "grpBio",
        }
    )
    # GP-08 tests account provisioning, not the separate elevation challenge.
    # Pre-authorize only the isolated browser fixture in the disposable CI DB.
    admin_row = auth_repository.find_user("gp08admin") or {}
    stamp = elevation.now()
    elevation.store_elevation(
        "gp08admin",
        elevated_at=stamp.isoformat(),
        expires_at=(stamp + dt.timedelta(hours=1)).isoformat(),
        session_version=int(admin_row.get("session_version") or 1),
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)
