"""Isolated real Flask fixture for F/G subtitle + total Golden Path E2E."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PORT = int(os.environ.get("TEACHER_AI_FG_FULLSTACK_PORT", "4177"))
STATE = Path(tempfile.mkdtemp(prefix="teacher-ai-fg-e2e-"))
os.environ.pop("DATABASE_URL", None)
os.environ.update({
    "TEACHER_SQLITE_PATH": str(STATE / "teacher.db"),
    "MATERIAL_STORAGE": str(STATE / "materials"),
    "SECRET_KEY": "isolated-ai-fg-e2e-secret-1234567890",
    "PRODUCTION_REQUIRE_SECRET": "false",
    "SESSION_COOKIE_SECURE": "false",
    "CSRF_ORIGIN_CHECK": "false",
    "CSP_ENFORCE": "true",
    "AI_EXTERNAL_PROCESSING_ENABLED": "true",
    "AI_EXTERNAL_MEDIA_ENABLED": "true",
    "TEACHER_E2E_TEST_MODE": "1",
    "TEACHER_E2E_DETERMINISTIC_STUBS": "1",
    "ASSET_VERSION": "aifge2e",
})

from teacher_app import create_app  # noqa: E402
from teacher_app.auth import accounts, repository as auth_repository  # noqa: E402
from teacher_app.materials import repository as materials  # noqa: E402
from teacher_app.storage import providers  # noqa: E402

app = create_app()
print(f"Isolated F/G database: {STATE / 'teacher.db'}", flush=True)
password = os.environ["TEACHER_CI_BROWSER_PASSWORD"]
if not auth_repository.find_user("e2eteacher"):
    accounts.create_account({
        "username": "e2eteacher", "password": password, "name": "E2E 臨床教師",
        "empId": "E2ET01", "role": "clinical_teacher",
        "roles": ["clinical_teacher", "group_leader"],
        "preferredArea": "internal", "preferredGroup": "grpBio",
    })
if not auth_repository.find_user("e2estudent"):
    accounts.create_account({
        "username": "e2estudent", "password": password, "name": "E2E 學員",
        "empId": "E2ES01", "role": "student", "roles": ["student"],
        "preferredArea": "internal", "preferredGroup": "grpBio",
    })

# Stable text source used by the combined G path.
source_text = (
    "E2E 教材：檢體收件後應核對病人識別、檢體種類與採檢時間。"
    "異常要依 SOP 回報。檢驗流程需注意檢體品質、實驗室安全及品質控制。\n"
)
text_key = "materials/e2e-source/source.txt"
providers.r2_client().put_object(
    Bucket=providers.R2_BUCKET_NAME, Key=text_key,
    Body=source_text.encode("utf-8"), ContentType="text/plain",
)
materials.insert_material({
    "id": "e2e-source", "filename": "e2e-source.txt", "title": "E2E 多來源教材",
    "description": "deterministic full-stack source", "category": "", "group_key": "grpBio",
    "training_area": "internal", "course_id": "", "folder": "e2e-source", "page_count": 1,
    "date_added": "2026-10-06", "storage_filename": "e2e-source.txt", "storage_backend": "r2",
    "storage_key": text_key, "slides_prefix": "", "storage_meta": "{}",
    "material_type": "standard", "atlas_meta": "{}", "active": True,
}, ignore_conflict=True)

# Real MP4 + AAC fixture. Subtitle runtime still performs the real media-source
# download/extraction; only speech recognition itself is deterministic in the
# isolated AI Worker.
video_dir = STATE / "fixture-video"
video_dir.mkdir(parents=True, exist_ok=True)
video_path = video_dir / "e2e-timed-video.mp4"
subprocess.run([
    os.environ.get("FFMPEG_PATH", "ffmpeg"), "-y",
    "-f", "lavfi", "-i", "color=c=navy:s=640x360:d=3:r=24",
    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=24000:duration=3",
    "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(video_path),
], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
video_key = "materials/e2e-video-source/source.mp4"
providers.r2_client().put_object(
    Bucket=providers.R2_BUCKET_NAME, Key=video_key,
    Body=video_path.read_bytes(), ContentType="video/mp4",
)
materials.insert_material({
    "id": "e2e-video-source", "filename": "e2e-timed-video.mp4",
    "title": "E2E-TEST-20261006 字幕時間點影片", "description": "timed-question source",
    "category": "", "group_key": "grpBio", "training_area": "internal", "course_id": "",
    "folder": "e2e-video-source", "page_count": 1, "date_added": "2026-10-06",
    "storage_filename": "e2e-timed-video.mp4", "storage_backend": "r2",
    "storage_key": video_key, "slides_prefix": "",
    "storage_meta": json.dumps({"durationSeconds": 3.0, "width": 640, "height": 360}, ensure_ascii=False),
    "material_type": "video", "atlas_meta": "{}", "active": True,
}, ignore_conflict=True)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)
