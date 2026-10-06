"""Isolated real Flask fixture for deterministic AI media full-stack E2E."""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PORT = int(os.environ.get("TEACHER_AI_MEDIA_FULLSTACK_PORT", "4176"))
STATE = Path(tempfile.mkdtemp(prefix="teacher-ai-media-e2e-"))
os.environ.pop("DATABASE_URL", None)
os.environ.update({
    "TEACHER_SQLITE_PATH": str(STATE / "teacher.db"), "MATERIAL_STORAGE": str(STATE / "materials"),
    "SECRET_KEY": "isolated-ai-media-e2e-secret-1234567890", "PRODUCTION_REQUIRE_SECRET": "false",
    "SESSION_COOKIE_SECURE": "false", "CSRF_ORIGIN_CHECK": "false", "CSP_ENFORCE": "true",
    "AI_EXTERNAL_PROCESSING_ENABLED": "true", "TEACHER_E2E_TEST_MODE": "1",
    "TEACHER_E2E_DETERMINISTIC_STUBS": "1", "ASSET_VERSION": "aimediae2e",
})

from teacher_app import create_app  # noqa: E402
from teacher_app.auth import accounts, repository as auth_repository  # noqa: E402
from teacher_app.materials import repository as materials  # noqa: E402
from teacher_app.storage import providers  # noqa: E402

app = create_app()
password = os.environ["TEACHER_CI_BROWSER_PASSWORD"]
if not auth_repository.find_user("e2eteacher"):
    accounts.create_account({"username": "e2eteacher", "password": password, "name": "E2E 臨床教師", "empId": "E2ET01", "role": "clinical_teacher", "roles": ["clinical_teacher"], "preferredArea": "internal", "preferredGroup": "grpBio"})

source = "E2E 教材：檢體收件後應核對病人識別、檢體種類與採檢時間。異常要依 SOP 回報。\n"
key = "materials/e2e-source/source.txt"
providers.r2_client().put_object(Bucket=providers.R2_BUCKET_NAME, Key=key, Body=source.encode("utf-8"), ContentType="text/plain")
materials.insert_material({"id": "e2e-source", "filename": "e2e-source.txt", "title": "E2E 多來源教材", "description": "deterministic full-stack source", "category": "", "group_key": "grpBio", "training_area": "internal", "course_id": "", "folder": "e2e-source", "page_count": 1, "date_added": "2026-10-06", "storage_filename": "e2e-source.txt", "storage_backend": "r2", "storage_key": key, "slides_prefix": "", "storage_meta": "{}", "material_type": "standard", "atlas_meta": "{}", "active": True}, ignore_conflict=True)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)
