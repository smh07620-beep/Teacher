"""Application configuration sourced from environment variables."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping

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


def external_media_hospital_cdn_hosts(
    env: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    """Return the explicit exact-host allowlist for hospital CDN media.

    The setting intentionally accepts hostnames/IP literals only: no schemes,
    paths, ports or wildcards.  YouTube/Vimeo are fixed providers and are not
    configured through this list.
    """

    source = os.environ if env is None else env
    raw = str(source.get("EXTERNAL_MEDIA_HOSPITAL_CDN_HOSTS", "") or "")
    hosts: list[str] = []
    for token in re.split(r"[,;\s]+", raw):
        host = token.strip().lower().rstrip(".")
        if host.startswith("[") and host.endswith("]"):
            host = host[1:-1]
        if (
            not host
            or "://" in host
            or "/" in host
            or "*" in host
            or host.count(":") == 1
        ):
            continue
        if host not in hosts:
            hosts.append(host)
    return tuple(hosts)


def _env_value(env: Mapping[str, str], name: str) -> str:
    return str(env.get(name, "") or "").strip()


def _env_truthy(env: Mapping[str, str], name: str, default: bool = False) -> bool:
    raw = env.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _warning(code: str, message: str, *, setting: str = "", level: str = "warning") -> dict:
    item = {"code": code, "level": level, "message": message}
    if setting:
        item["setting"] = setting
    return item


def _missing_settings(env: Mapping[str, str], names: tuple[str, ...]) -> list[str]:
    return [name for name in names if not _env_value(env, name)]


def deployment_config_warnings(env: Mapping[str, str] | None = None) -> list[dict]:
    """Return actionable deployment warnings without exposing secret values.

    Local development intentionally supports SQLite and a development session
    secret.  Production validation activates on Render or when the existing
    ``PRODUCTION_REQUIRE_SECRET`` switch is enabled.  Provider groups are also
    checked when explicitly selected so a bad storage choice is visible before
    the first upload request.
    """

    source = os.environ if env is None else env
    production = _env_truthy(source, "RENDER") or _env_truthy(
        source, "PRODUCTION_REQUIRE_SECRET"
    )
    warnings: list[dict] = []

    if production and not _env_value(source, "DATABASE_URL"):
        warnings.append(
            _warning(
                "database_url_missing",
                "DATABASE_URL 未設定；正式部署不可依賴容器內 SQLite。請設定持久化 PostgreSQL 連線字串。",
                setting="DATABASE_URL",
                level="error",
            )
        )

    if production:
        configured_secret = _env_value(source, "SECRET_KEY")
        if len(configured_secret) < 32:
            warnings.append(
                _warning(
                    "secret_key_invalid",
                    "SECRET_KEY 必須明確設定且至少 32 字元；不可使用 ADMIN_KEY 或開發預設值作為正式 session secret。",
                    setting="SECRET_KEY",
                    level="error",
                )
            )
        if not _env_value(source, "ADMIN_KEY"):
            warnings.append(
                _warning(
                    "admin_key_missing",
                    "ADMIN_KEY 未設定；需要短效管理權限提升的敏感操作將無法完成重新驗證。",
                    setting="ADMIN_KEY",
                )
            )

        ai_enabled = _env_truthy(source, "AI_EXTERNAL_PROCESSING_ENABLED", True)
        ai_provider = _env_value(source, "AI_PROVIDER").lower() or "groq"
        if ai_enabled and ai_provider in {"groq", "auto"} and not _env_value(source, "GROQ_API_KEY"):
            warnings.append(
                _warning(
                    "groq_api_key_missing",
                    "外部 AI 已啟用且使用 Groq/auto；請設定 GROQ_API_KEY，否則 AI 出題/轉錄不可用。",
                    setting="GROQ_API_KEY",
                )
            )

        background_jobs = _env_truthy(source, "MATERIAL_BACKGROUND_JOBS", True)
        worker_enabled = _env_truthy(source, "MATERIAL_WORKER_ENABLED", True)
        if (background_jobs or worker_enabled) and not _env_value(source, "MATERIAL_WORKER_TOKEN"):
            warnings.append(
                _warning(
                    "material_worker_token_missing",
                    "教材背景工作或 Worker API 已啟用；請設定 MATERIAL_WORKER_TOKEN，否則可信任 Worker 無法驗證。",
                    setting="MATERIAL_WORKER_TOKEN",
                )
            )

    primary_backend = _env_value(source, "MATERIAL_STORAGE_BACKEND").lower() or "auto"
    fallback_backend = _env_value(source, "STORAGE_FALLBACK_BACKEND").lower()
    staging_backend = _env_value(source, "MATERIAL_SHARED_STAGING_BACKEND").lower() or "auto"
    requested_backends = {primary_backend, staging_backend}
    if _env_truthy(source, "STORAGE_FAILOVER_ON_FULL") and fallback_backend:
        requested_backends.add(fallback_backend)

    provider_groups = {
        "r2": (
            ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME"),
            "Cloudflare R2",
        ),
        "mega": (("MEGA_EMAIL", "MEGA_PASSWORD"), "MEGA"),
        "gdrive": (
            ("GDRIVE_CLIENT_ID", "GDRIVE_CLIENT_SECRET", "GDRIVE_REFRESH_TOKEN", "GDRIVE_FOLDER_ID"),
            "Google Drive",
        ),
    }
    for backend, (names, label) in provider_groups.items():
        values_present = any(_env_value(source, name) for name in names)
        required = backend in requested_backends
        if not required and not values_present:
            continue
        missing = _missing_settings(source, names)
        if missing:
            warnings.append(
                _warning(
                    f"{backend}_credentials_incomplete",
                    f"{label} 設定不完整；缺少：{', '.join(missing)}。請補齊該 provider 的環境變數。",
                    setting=f"{backend.upper()}_CREDENTIALS",
                )
            )

    try:
        web_concurrency = max(1, int(_env_value(source, "WEB_CONCURRENCY") or "1"))
    except ValueError:
        web_concurrency = 1
        warnings.append(
            _warning(
                "web_concurrency_invalid",
                "WEB_CONCURRENCY 必須是正整數；目前會使用單一 Gunicorn worker 預設值。",
                setting="WEB_CONCURRENCY",
            )
        )
    if production and web_concurrency > 1:
        warnings.append(
            _warning(
                "login_rate_limit_process_local",
                "登入失敗限流目前是 process-local；WEB_CONCURRENCY>1 會讓計數分散。現有支援拓撲為單一 Web process/instance。",
                setting="WEB_CONCURRENCY",
            )
        )

    return warnings


def deployment_config_status(env: Mapping[str, str] | None = None) -> dict:
    warnings = deployment_config_warnings(env)
    return {
        "ok": not any(item.get("level") == "error" for item in warnings),
        "warnings": warnings,
    }


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
    hospital_cdn_hosts = external_media_hospital_cdn_hosts()
    app.config["EXTERNAL_MEDIA_HOSPITAL_CDN_HOSTS"] = hospital_cdn_hosts
    # Compatibility seam for existing question/media validators.  Production
    # ownership is the EXTERNAL_MEDIA_HOSPITAL_CDN_HOSTS environment setting.
    app.config["DIRECT_MEDIA_ALLOWLIST"] = hospital_cdn_hosts
    app.config["DEPLOYMENT_CONFIGURATION"] = deployment_config_status()
    for item in app.config["DEPLOYMENT_CONFIGURATION"]["warnings"]:
        log = app.logger.error if item.get("level") == "error" else app.logger.warning
        log(
            "deployment_config code=%s setting=%s message=%s",
            item.get("code", "unknown"),
            item.get("setting", ""),
            item.get("message", ""),
        )
