"""Application configuration sourced from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
BASE_DIR = PACKAGE_DIR.parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
_RESOLVED_MATERIAL_STORAGE: Path | None = None


@dataclass(frozen=True)
class StoragePaths:
    base_dir: Path
    static_dir: Path
    slides_dir: Path
    material_storage: Path
    upload_dir: Path
    question_images_dir: Path
    uploaded_slides_dir: Path
    doc_templates_dir: Path
    pgy_assessment_templates_dir: Path
    data_dir: Path
    tmp_dir: Path
    upload_progress_dir: Path
    preview_cache_dir: Path

    def with_runtime_overrides(
        self,
        *,
        material_storage=None,
        uploaded_slides_dir=None,
    ) -> "StoragePaths":
        """Return a copy with explicitly injected runtime compatibility paths.

        Canonical configuration remains the owner of the path set; callers that
        need to honor a temporary compatibility override (for example a legacy
        test seam) can inject only the affected paths without teaching domain
        code about legacy module globals.
        """
        changes = {}
        if material_storage is not None:
            changes["material_storage"] = Path(material_storage)
        if uploaded_slides_dir is not None:
            changes["uploaded_slides_dir"] = Path(uploaded_slides_dir)
        return replace(self, **changes) if changes else self


def storage_paths(*, ensure: bool = True) -> StoragePaths:
    """Resolve every local storage path from one canonical configuration seam."""
    global _RESOLVED_MATERIAL_STORAGE
    material_storage = _RESOLVED_MATERIAL_STORAGE or Path(
        os.environ.get("MATERIAL_STORAGE", "/var/data/materials")
    )
    if ensure:
        try:
            material_storage.mkdir(parents=True, exist_ok=True)
        except OSError:
            material_storage = BASE_DIR / "uploads"
            material_storage.mkdir(parents=True, exist_ok=True)
        _RESOLVED_MATERIAL_STORAGE = material_storage
    paths = StoragePaths(
        base_dir=BASE_DIR,
        static_dir=STATIC_DIR,
        slides_dir=STATIC_DIR / "slides",
        material_storage=material_storage,
        upload_dir=material_storage / "ppt",
        question_images_dir=material_storage / "question_images",
        uploaded_slides_dir=material_storage / "slides",
        doc_templates_dir=material_storage / "doc_templates",
        pgy_assessment_templates_dir=material_storage / "pgy_assessment_templates",
        data_dir=DATA_DIR,
        tmp_dir=BASE_DIR / "tmp_convert",
        upload_progress_dir=BASE_DIR / "tmp_convert" / "upload_progress",
        preview_cache_dir=BASE_DIR / "tmp_convert" / "preview_cache",
    )
    if ensure:
        for directory in (
            paths.slides_dir,
            paths.upload_dir,
            paths.question_images_dir,
            paths.uploaded_slides_dir,
            paths.doc_templates_dir,
            paths.pgy_assessment_templates_dir,
            paths.data_dir,
            paths.tmp_dir,
            paths.upload_progress_dir,
            paths.preview_cache_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
    return paths


def database_url() -> str:
    return os.environ.get("DATABASE_URL", "").strip()


def sqlite_path() -> Path:
    override = os.environ.get("TEACHER_SQLITE_PATH", "").strip()
    if override:
        return Path(override)
    return DATA_DIR / "exam_records.db"


def secret_key() -> str:
    return os.environ.get("SECRET_KEY", "").strip() or admin_key() or "local-development-only-change-me"


def admin_key() -> str:
    """Return the optional compatibility administrator key from live config."""
    return os.environ.get("ADMIN_KEY", "").strip()


def max_upload_mb() -> int:
    try:
        value = int(os.environ.get("MAX_UPLOAD_MB", "250"))
    except ValueError:
        value = 250
    return max(1, min(512, value))


def material_preview_cache_mb() -> int:
    try:
        value = int(os.environ.get("MATERIAL_PREVIEW_CACHE_MB", "512"))
    except ValueError:
        value = 512
    return max(64, min(2048, value))


def material_preview_cache_ttl_seconds() -> int:
    try:
        value = int(os.environ.get("MATERIAL_PREVIEW_CACHE_TTL_SECONDS", "21600"))
    except ValueError:
        value = 21600
    return max(300, min(86400, value))


def teaching_usage_notice() -> str:
    return os.environ.get("TEACHING_USAGE_NOTICE", "教學專用・不得轉發、轉載、販售").strip() or "教學專用・不得轉發、轉載、販售"


def configure_app(app) -> None:
    app.config["SECRET_KEY"] = secret_key()
    app.config["MAX_CONTENT_LENGTH"] = max_upload_mb() * 1024 * 1024
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    app.config["SQL_DATABASE_URL"] = database_url()
    app.config["SQLITE_PATH"] = str(sqlite_path())
    app.config["STORAGE_PATHS"] = storage_paths()
