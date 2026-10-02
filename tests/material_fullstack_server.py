"""Real Flask fixture for Browser -> R2 -> material Worker full-stack CI."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PORT = int(os.environ.get("TEACHER_MATERIAL_FULLSTACK_PORT", "4175"))
STATE_DIR = Path(tempfile.mkdtemp(prefix="teacher-material-fullstack-"))

os.environ.pop("DATABASE_URL", None)
os.environ["TEACHER_SQLITE_PATH"] = str(STATE_DIR / "teacher-material-fullstack.db")
os.environ["MATERIAL_STORAGE"] = str(STATE_DIR / "materials")
os.environ["SECRET_KEY"] = os.environ.get(
    "TEACHER_MATERIAL_FULLSTACK_SECRET",
    "teacher-material-fullstack-ci-secret-1234567890",
)
os.environ["PRODUCTION_REQUIRE_SECRET"] = "false"
os.environ["SESSION_COOKIE_SECURE"] = "false"
os.environ["CSRF_ORIGIN_CHECK"] = "false"
os.environ["CSP_ENFORCE"] = "true"
os.environ["MATERIAL_BACKGROUND_JOBS"] = "false"
os.environ["MATERIAL_WORKER_ENABLED"] = "true"
os.environ["MATERIAL_DIRECT_UPLOAD_ENABLED"] = "true"
os.environ["MATERIAL_DIRECT_UPLOAD_MAX_MB"] = "64"
os.environ["MATERIAL_WEB_BYTE_UPLOAD_ENABLED"] = "false"
os.environ["MATERIAL_STORAGE_BACKEND"] = "r2"
os.environ["MATERIAL_SHARED_STAGING_BACKEND"] = "r2"
os.environ["AI_EXTERNAL_PROCESSING_ENABLED"] = "false"
os.environ["ASSET_VERSION"] = "materialfullstackci"

required = (
    "R2_ENDPOINT_URL",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET_NAME",
    "MATERIAL_WORKER_TOKEN",
    "TEACHER_CI_BROWSER_PASSWORD",
)
missing = [name for name in required if not str(os.environ.get(name) or "").strip()]
if missing:
    raise RuntimeError("Missing material full-stack CI settings: " + ", ".join(missing))

from teacher_app import create_app  # noqa: E402
from teacher_app.auth import accounts, repository as auth_repository  # noqa: E402
from teacher_app.courses import repository as course_repository  # noqa: E402


app = create_app()


def _seed_account() -> None:
    if auth_repository.find_user("gp01teacher"):
        return
    accounts.create_account(
        {
            "username": "gp01teacher",
            "password": os.environ["TEACHER_CI_BROWSER_PASSWORD"],
            "name": "GP01 教材教師",
            "empId": "GP0101",
            "role": "clinical_teacher",
            "roles": ["clinical_teacher"],
            "preferredArea": "internal",
            "preferredGroup": "grpBio",
        }
    )


def _seed_course() -> None:
    if course_repository.get_course("course-full-stack"):
        return
    course_repository.create_course(
        course_id="course-full-stack",
        area="internal",
        group="grpBio",
        title="Full-stack Golden Path 課程",
        description="Browser → R2 → Worker → Database → Browser",
        date_added="2026-10-02T00:00:00+00:00",
    )


_seed_account()
_seed_course()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)
