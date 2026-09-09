"""Application configuration sourced from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
BASE_DIR = PACKAGE_DIR.parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", "").strip()


def sqlite_path() -> Path:
    override = os.environ.get("TEACHER_SQLITE_PATH", "").strip()
    if override:
        return Path(override)
    return DATA_DIR / "exam_records.db"


def secret_key() -> str:
    admin_key = os.environ.get("ADMIN_KEY", "").strip()
    return os.environ.get("SECRET_KEY", "").strip() or admin_key or "local-development-only-change-me"


def max_upload_mb() -> int:
    try:
        value = int(os.environ.get("MAX_UPLOAD_MB", "250"))
    except ValueError:
        value = 250
    return max(1, min(512, value))


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
