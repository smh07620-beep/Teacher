"""Canonical storage administration workflows.

This module owns provider-neutral status aggregation and material migration
orchestration. Provider credentials, SDK clients and provider protocols stay in
``teacher_app.storage.providers`` or are injected through ``StorageAdminRuntime``
while the legacy host is being retired.
"""
from __future__ import annotations

import json
import os
import shutil
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, MutableMapping

from teacher_app.materials import repository as material_repository
from teacher_app.materials import storage as material_storage
from teacher_app.storage import providers
from teacher_app.storage.worker_runtime import WorkerMaterialStorageAdapter


_STATUS_CACHE = {"at": 0.0, "data": None}
_STATUS_LOCK = threading.RLock()


def _env_true(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return bool(default)
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _cache_seconds() -> int:
    try:
        value = int(os.environ.get("STORAGE_STATUS_CACHE_SECONDS", "30"))
    except (TypeError, ValueError):
        value = 30
    return max(5, min(300, value))


@dataclass
class StorageAdminRuntime:
    """Injected runtime seams for storage-admin compatibility behavior."""

    paths_provider: Callable[[], Any]
    active_material_backend: Callable[[], str]
    fallback_backend_ready: Callable[[], Any]
    gdrive_is_configured: Callable[[], bool]
    gdrive_check: Callable[[], dict]
    mega_is_configured: Callable[[], bool]
    mega_storage_space: Callable[[], dict]
    oci_is_configured: Callable[[], bool]
    oci_bucket_usage_bytes: Callable[[], int]
    r2_is_configured: Callable[[], bool]
    upload_material_tree_to_gdrive: Callable[..., tuple[str, str, dict]]
    upload_material_tree_to_r2: Callable[..., tuple[str, str]]
    r2_delete_prefix: Callable[[str], None]
    download_material_from_r2: Callable[[dict, Path, Path], None] | None = None
    configured_mode: str = "auto"
    fallback_backend: str = ""
    failover_on_full: bool = False
    free_only_mode: bool = True
    mega_free_limit_gb: float = 18.0
    oci_free_limit_gb: float = 19.5
    oci_presign_seconds: int = 3600
    r2_presign_seconds: int = 3600
    cache_seconds: int = 30
    status_cache: MutableMapping[str, Any] | None = None
    status_lock: Any = None


def build_canonical_runtime(
    *,
    paths_provider: Callable[[], Any],
    r2_record_object: Callable[[str, int], None] | None = None,
    r2_record_deleted: Callable[[str], None] | None = None,
    storage_adapter: WorkerMaterialStorageAdapter | None = None,
) -> StorageAdminRuntime:
    """Compose storage-admin behavior from canonical provider owners.

    R2 ledger mutation still belongs to the compatibility host.  Callers inject
    only the two accounting callbacks until that owner is extracted.
    """

    storage = storage_adapter or WorkerMaterialStorageAdapter()

    def gdrive_check():
        info = providers.gdrive_service().files().get(
            fileId=providers.GDRIVE_FOLDER_ID,
            fields="id,name,mimeType,trashed",
        ).execute()
        if info.get("trashed"):
            raise RuntimeError("Google Drive 教材根資料夾目前在垃圾桶中。")
        if info.get("mimeType") != "application/vnd.google-apps.folder":
            raise RuntimeError("GDRIVE_FOLDER_ID 不是 Google Drive 資料夾。")
        return info

    def fallback_backend_ready():
        enabled = _env_true("STORAGE_FAILOVER_ON_FULL", False)
        requested = os.environ.get("STORAGE_FALLBACK_BACKEND", "").strip().lower()
        if enabled and requested == "gdrive" and providers.gdrive_is_configured():
            return "gdrive"
        return ""

    def oci_bucket_usage_bytes():
        return material_storage.bucket_usage_bytes(
            providers.oci_client(),
            providers.OCI_BUCKET_NAME,
        )

    def upload_material_tree_to_r2(material_id, source_path, slides_dir, page_count):
        if r2_record_object is None:
            raise RuntimeError("R2 使用量 ledger callback 尚未注入。")
        client = providers.r2_client()
        source_path = Path(source_path)
        slides_dir = Path(slides_dir)
        source_key = f"materials/{material_id}/source{source_path.suffix.lower()}"
        slides_prefix = f"materials/{material_id}/slides"

        def upload(path: Path, key: str):
            client.upload_file(
                str(path),
                providers.R2_BUCKET_NAME,
                key,
                ExtraArgs={"ContentType": storage._content_type(path)},
            )
            r2_record_object(key, path.stat().st_size)

        upload(source_path, source_key)
        for index in range(1, int(page_count or 0) + 1):
            slide = storage._slide_local_path(slides_dir, index)
            if slide.exists():
                upload(slide, f"{slides_prefix}/{slide.name}")
        return source_key, slides_prefix

    def r2_delete_prefix(prefix: str):
        if r2_record_deleted is None:
            raise RuntimeError("R2 使用量 ledger delete callback 尚未注入。")
        material_storage.delete_prefix(
            providers.r2_client(),
            providers.R2_BUCKET_NAME,
            prefix,
            on_deleted=r2_record_deleted,
        )

    def download_material_from_r2(entry: dict, source: Path, slides: Path):
        client = providers.r2_client()
        source_key = str(entry.get("storageKey") or "")
        if not source_key:
            raise RuntimeError("此教材缺少 R2 原始檔 key。")
        source.parent.mkdir(parents=True, exist_ok=True)
        slides.mkdir(parents=True, exist_ok=True)
        client.download_file(providers.R2_BUCKET_NAME, source_key, str(source))
        prefix = str(entry.get("slidesPrefix") or "").rstrip("/")
        if not prefix:
            return
        for page in material_storage.iter_s3_pages(
            client,
            providers.R2_BUCKET_NAME,
            prefix=prefix + "/",
        ):
            for item in page.get("Contents", []):
                key = str(item.get("Key") or "")
                if not key or key.endswith("/"):
                    continue
                name = Path(key).name
                client.download_file(
                    providers.R2_BUCKET_NAME,
                    key,
                    str(slides / name),
                )

    return StorageAdminRuntime(
        paths_provider=paths_provider,
        active_material_backend=storage.active_backend,
        fallback_backend_ready=fallback_backend_ready,
        gdrive_is_configured=providers.gdrive_is_configured,
        gdrive_check=gdrive_check,
        mega_is_configured=storage.mega_is_configured,
        mega_storage_space=storage._mega_storage_space,
        oci_is_configured=providers.oci_is_configured,
        oci_bucket_usage_bytes=oci_bucket_usage_bytes,
        r2_is_configured=providers.r2_is_configured,
        upload_material_tree_to_gdrive=storage.upload_material_tree_to_gdrive,
        upload_material_tree_to_r2=upload_material_tree_to_r2,
        r2_delete_prefix=r2_delete_prefix,
        download_material_from_r2=download_material_from_r2,
        configured_mode=storage.requested_backend,
        fallback_backend=os.environ.get("STORAGE_FALLBACK_BACKEND", "").strip().lower(),
        failover_on_full=_env_true("STORAGE_FAILOVER_ON_FULL", False),
        free_only_mode=storage.free_only,
        mega_free_limit_gb=providers.MEGA_STORAGE_LIMIT_GB,
        oci_free_limit_gb=providers.OCI_FREE_LIMIT_GB,
        oci_presign_seconds=providers.OCI_PRESIGN_SECONDS,
        r2_presign_seconds=providers.R2_PRESIGN_SECONDS,
        cache_seconds=_cache_seconds(),
        status_cache=_STATUS_CACHE,
        status_lock=_STATUS_LOCK,
    )


def storage_status(runtime: StorageAdminRuntime, *, force: bool = False) -> dict:
    """Return the established storage status JSON payload."""
    cache = runtime.status_cache
    lock = runtime.status_lock
    now = time.time()
    if cache is not None and lock is not None:
        with lock:
            cached = cache.get("data")
            cached_at = float(cache.get("at", 0) or 0)
            if not force and cached is not None and (now - cached_at) < runtime.cache_seconds:
                return cached

    try:
        backend = runtime.active_material_backend()
        error = ""
    except Exception as exc:
        backend = "error"
        error = str(exc)

    drive_info = None
    drive_error = ""
    if backend == "gdrive" and runtime.gdrive_is_configured():
        try:
            drive_info = runtime.gdrive_check()
        except Exception as exc:
            drive_error = str(exc)
            if not error:
                error = drive_error

    materials = material_repository.list_uploaded_materials(include_inactive=True)

    mega_space_info = None
    mega_status_error = ""
    if backend == "mega" and runtime.mega_is_configured():
        try:
            space = runtime.mega_storage_space()
            mega_space_info = {
                "usedGb": round(space["used"] / 1024**3, 3),
                "totalGb": round(space["total"] / 1024**3, 3),
            }
        except Exception as exc:
            mega_status_error = str(exc)
            if not error:
                error = mega_status_error

    oci_used = None
    if backend == "oci" and runtime.oci_is_configured():
        try:
            oci_used = round(runtime.oci_bucket_usage_bytes() / 1024**3, 3)
        except Exception as exc:
            if not error:
                error = str(exc)

    data = {
        "configuredMode": runtime.configured_mode,
        "activeBackend": backend,
        "fallbackBackend": runtime.fallback_backend,
        "failoverOnFull": runtime.failover_on_full,
        "fallbackReady": bool(runtime.fallback_backend_ready()),
        "gdriveConfigured": runtime.gdrive_is_configured(),
        "gdriveConnected": bool(drive_info),
        "gdriveFolderName": (drive_info or {}).get("name", ""),
        "megaConfigured": runtime.mega_is_configured(),
        "megaFreeOnly": runtime.free_only_mode,
        "megaFreeLimitGb": runtime.mega_free_limit_gb,
        "megaSpace": mega_space_info,
        "megaError": mega_status_error,
        "ociConfigured": runtime.oci_is_configured(),
        "ociFreeOnly": runtime.free_only_mode,
        "ociFreeLimitGb": runtime.oci_free_limit_gb,
        "ociUsedGb": oci_used,
        "r2Configured": runtime.r2_is_configured(),
        "presignSeconds": runtime.oci_presign_seconds if backend == "oci" else runtime.r2_presign_seconds,
        "materials": {
            "mega": sum(1 for item in materials if item.get("storageBackend") == "mega"),
            "oci": sum(1 for item in materials if item.get("storageBackend") == "oci"),
            "gdrive": sum(1 for item in materials if item.get("storageBackend") == "gdrive"),
            "r2": sum(1 for item in materials if item.get("storageBackend") == "r2"),
            "local": sum(
                1
                for item in materials
                if item.get("storageBackend") not in {"mega", "oci", "gdrive", "r2"}
            ),
        },
        "error": error,
        "cachedSeconds": runtime.cache_seconds,
    }
    if cache is not None and lock is not None:
        with lock:
            cache.update({"at": time.time(), "data": data})
    return data


def migrate_materials_to_gdrive(runtime: StorageAdminRuntime) -> tuple[dict, int]:
    """Preserve the existing local/R2 -> Google Drive migration contract."""
    if not runtime.gdrive_is_configured():
        return {
            "error": "Google Drive 尚未設定完成，無法搬移。請先設定 OAuth refresh token 與 GDRIVE_FOLDER_ID。"
        }, 400
    try:
        runtime.gdrive_check()
    except Exception as exc:
        return {"error": f"Google Drive 連線/資料夾檢查失敗：{exc}"}, 400

    paths = runtime.paths_provider()
    migrated, skipped, failed = 0, [], []
    for entry in material_repository.list_uploaded_materials(include_inactive=True):
        old_backend = entry.get("storageBackend", "local")
        if old_backend == "gdrive":
            continue
        temp_root = None
        try:
            if old_backend == "r2":
                if not runtime.r2_is_configured():
                    raise RuntimeError("此教材在 R2，但目前 Render 未設定 R2 金鑰，無法讀出後搬移。")
                temp_root = paths.tmp_dir / f"migrate-{entry['id']}-{uuid.uuid4().hex[:6]}"
                source_dir = temp_root / "source"
                slides = temp_root / "slides"
                source_dir.mkdir(parents=True, exist_ok=True)
                slides.mkdir(parents=True, exist_ok=True)
                ext = Path(entry.get("storageFilename") or entry.get("filename") or "source.bin").suffix or ".bin"
                source = source_dir / f"source{ext}"
                if runtime.download_material_from_r2 is None:
                    # Preserve the current compatibility-host failure shape until
                    # a canonical R2 tree downloader is composed at the boundary.
                    raise NameError("name '_download_material_from_r2' is not defined")
                runtime.download_material_from_r2(entry, source, slides)
            else:
                source = paths.upload_dir / entry["id"] / entry.get("storageFilename", "")
                slides = paths.uploaded_slides_dir / entry.get("folder", entry["id"])
                if not source.exists():
                    skipped.append({
                        "id": entry["id"],
                        "title": entry.get("title", ""),
                        "reason": "本機原始檔不存在",
                    })
                    continue

            key, prefix, meta = runtime.upload_material_tree_to_gdrive(
                entry["id"],
                source,
                slides,
                entry.get("pageCount", 0),
                original_name=entry.get("filename"),
            )
            material_repository.update_material_storage(
                entry["id"],
                backend="gdrive",
                storage_key=key,
                slides_prefix=prefix,
                storage_meta_json=json.dumps(meta, ensure_ascii=False),
            )

            if old_backend == "r2":
                runtime.r2_delete_prefix(f"materials/{entry['id']}/")
            else:
                shutil.rmtree(paths.upload_dir / entry["id"], ignore_errors=True)
                shutil.rmtree(
                    paths.uploaded_slides_dir / entry.get("folder", entry["id"]),
                    ignore_errors=True,
                )
            migrated += 1
        except Exception as exc:
            failed.append({
                "id": entry["id"],
                "title": entry.get("title", ""),
                "reason": str(exc)[:500],
            })
        finally:
            if temp_root:
                shutil.rmtree(temp_root, ignore_errors=True)

    return {
        "ok": len(failed) == 0,
        "migrated": migrated,
        "skipped": skipped,
        "failed": failed,
    }, 200


def migrate_materials_to_r2(runtime: StorageAdminRuntime) -> tuple[dict, int]:
    """Preserve the existing local -> R2 migration and rollback semantics."""
    if not runtime.r2_is_configured():
        return {"error": "R2 尚未設定完成，無法搬移。"}, 400

    paths = runtime.paths_provider()
    migrated, skipped, failed = 0, [], []
    for entry in material_repository.list_uploaded_materials(include_inactive=True):
        backend = entry.get("storageBackend")
        if backend == "r2":
            continue
        if backend == "gdrive":
            skipped.append({
                "id": entry["id"],
                "title": entry.get("title", ""),
                "reason": "目前已在 Google Drive；R2 搬移工具僅處理本機教材",
            })
            continue
        source = paths.upload_dir / entry["id"] / entry.get("storageFilename", "")
        slides = paths.uploaded_slides_dir / entry.get("folder", entry["id"])
        if not source.exists():
            skipped.append({
                "id": entry["id"],
                "title": entry.get("title", ""),
                "reason": "本機原始檔不存在",
            })
            continue
        try:
            key, prefix = runtime.upload_material_tree_to_r2(
                entry["id"], source, slides, entry.get("pageCount", 0)
            )
            material_repository.update_material_storage(
                entry["id"],
                backend="r2",
                storage_key=key,
                slides_prefix=prefix,
            )
            shutil.rmtree(paths.upload_dir / entry["id"], ignore_errors=True)
            shutil.rmtree(slides, ignore_errors=True)
            migrated += 1
        except Exception as exc:
            try:
                runtime.r2_delete_prefix(f"materials/{entry['id']}/")
            except Exception:
                pass
            failed.append({
                "id": entry["id"],
                "title": entry.get("title", ""),
                "reason": str(exc)[:300],
            })

    return {
        "ok": len(failed) == 0,
        "migrated": migrated,
        "skipped": skipped,
        "failed": failed,
    }, 200


__all__ = [
    "StorageAdminRuntime",
    "build_canonical_runtime",
    "migrate_materials_to_gdrive",
    "migrate_materials_to_r2",
    "storage_status",
]
