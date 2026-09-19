"""Canonical shared staging transport for background material jobs.

This is the Web/worker hand-off store.  Credentials and SDK/session creation stay
in :mod:`teacher_app.storage.providers`; R2 quota/reservation policy stays in
``storage.r2_budget`` and usage observations in ``storage.r2_ledger``.
"""
from __future__ import annotations

import hashlib
import mimetypes
import os
import re
import shutil
from pathlib import Path

from teacher_app.config import max_upload_mb, storage_paths
from teacher_app.materials.sync_runtime import is_mega_capacity_full_error
from teacher_app.materials.validation import ALLOWED_MATERIAL_EXTENSIONS
from teacher_app.storage import providers, r2_budget, r2_ledger
from teacher_app.storage.worker_runtime import WorkerMaterialStorageAdapter
from teacher_app.storage.web_runtime import WebStorageRuntime


def _env_true(name: str, default: bool) -> bool:
    fallback = "true" if default else "false"
    return os.environ.get(name, fallback).strip().lower() in {"1", "true", "yes", "on"}


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _ascii_metadata(metadata) -> dict[str, str]:
    return {
        str(key).encode("ascii", "backslashreplace").decode("ascii")[:1024]:
        str(value).encode("ascii", "backslashreplace").decode("ascii")[:1024]
        for key, value in dict(metadata or {}).items()
    }


class MaterialStagingRuntime:
    def __init__(self, paths_provider=storage_paths, *, storage_adapter=None):
        self.paths_provider = paths_provider
        self.storage = storage_adapter or WorkerMaterialStorageAdapter()

    @staticmethod
    def _requested_backend() -> str:
        return (
            os.environ.get("MATERIAL_SHARED_STAGING_BACKEND", "auto").strip().lower()
            or "auto"
        )

    def shared_backend(self) -> str:
        requested = self._requested_backend()
        if requested not in {"auto", "r2", "mega", "gdrive", "local"}:
            raise RuntimeError(
                "MATERIAL_SHARED_STAGING_BACKEND 必須是 auto、r2、mega、gdrive 或 local。"
            )
        if requested == "r2":
            if not providers.r2_is_configured():
                raise RuntimeError("Shared Staging 設為 R2，但 R2 尚未完成設定。")
            return "r2"
        if requested == "mega":
            if not self.storage.mega_is_configured():
                raise RuntimeError("Shared Staging 設為 MEGA，但 MEGA 尚未完成設定。")
            return "mega"
        if requested == "gdrive":
            if not providers.gdrive_is_configured():
                raise RuntimeError("Shared Staging 設為 Google Drive，但 OAuth 尚未完成設定。")
            return "gdrive"
        if requested == "local":
            return "local"
        if providers.r2_is_configured():
            return "r2"
        backend = self.storage.active_backend()
        return backend if backend in {"mega", "gdrive"} else "local"

    def capability(self) -> dict:
        try:
            backend = self.shared_backend()
            return {
                "available": True,
                "backend": backend,
                "shared": backend in {"r2", "mega", "gdrive"},
                "namespace": "_staging/material-jobs",
            }
        except Exception as exc:
            return {
                "available": False,
                "backend": "",
                "shared": False,
                "namespace": "_staging/material-jobs",
                "reason": str(exc)[:180],
            }

    @staticmethod
    def safe_name(job_id: str, original_name: str) -> str:
        ext = Path(original_name or "source.bin").suffix.lower()
        if ext not in ALLOWED_MATERIAL_EXTENSIONS:
            raise ValueError("Shared Staging 檔案副檔名不受支援。")
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "", str(job_id or ""))[:80]
        if not safe_id:
            raise ValueError("背景工作 ID 不合法。")
        return f"source{ext}"

    @staticmethod
    def _gdrive_find_file_in_folder(folder_id: str, filename: str) -> str:
        return WebStorageRuntime.gdrive_find_file_in_folder(folder_id, filename)

    def _gdrive_staging_parent(self) -> str:
        service = providers.gdrive_service()
        root = self._gdrive_find_file_in_folder(providers.GDRIVE_FOLDER_ID, "_staging")
        if not root:
            root = self.storage._gdrive_create_folder(
                service,
                "_staging",
                providers.GDRIVE_FOLDER_ID,
                {"smh_kind": "staging"},
            )
        jobs = self._gdrive_find_file_in_folder(root, "material-jobs")
        if not jobs:
            jobs = self.storage._gdrive_create_folder(
                service,
                "material-jobs",
                root,
                {"smh_kind": "material_job_staging"},
            )
        return jobs

    def _gdrive_upload_staging(self, source: Path, job_id: str, name: str) -> str:
        service = providers.gdrive_service()
        uploaded = self.storage._gdrive_upload_file(
            service,
            source,
            f"{job_id}-{name}",
            self._gdrive_staging_parent(),
            {"smh_kind": "material_job_staging", "smh_job_id": str(job_id)},
        )
        return str(uploaded["id"])

    @staticmethod
    def _mega_failover_ready() -> bool:
        return bool(
            _env_true("STORAGE_FAILOVER_ON_FULL", False)
            and os.environ.get("STORAGE_FALLBACK_BACKEND", "").strip().lower() == "gdrive"
            and providers.gdrive_is_configured()
        )

    def upload(self, source: Path, job_id: str, original_name: str):
        source = Path(source)
        if not source.is_file() or source.stat().st_size <= 0:
            raise ValueError("Shared Staging 原始檔不存在或空白。")
        if source.stat().st_size > max_upload_mb() * 1024 * 1024:
            raise ValueError("教材檔案超過上傳大小限制。")
        name = self.safe_name(job_id, original_name)
        backend = self.shared_backend()
        if backend == "r2":
            key = f"_staging/material-jobs/{job_id}/{name}"
            reserved = False
            if r2_budget.large_file(source.stat().st_size):
                r2_budget.enforce_large_upload_budget(job_id, key, source.stat().st_size)
                reserved = True
            try:
                providers.r2_client().upload_file(
                    str(source),
                    providers.R2_BUCKET_NAME,
                    key,
                    ExtraArgs={
                        "ContentType": mimetypes.guess_type(str(source))[0]
                        or "application/octet-stream",
                        "Metadata": _ascii_metadata(
                            {
                                "jobid": job_id,
                                "expectedbytes": source.stat().st_size,
                                "sha256": _sha256_file(source),
                                "createdat": __import__("datetime").datetime.now(
                                    __import__("datetime").timezone.utc
                                ).isoformat(),
                            }
                        ),
                    },
                )
                r2_ledger.record_object(key, source.stat().st_size)
            except Exception:
                if reserved:
                    r2_budget.release_reservation(job_id, "staging_upload_failed")
                raise
            if reserved:
                r2_budget.release_reservation(job_id, "staging_created")
            return "r2", key, ""

        if backend == "mega":
            try:
                self.storage._mega_free_guard(source.stat().st_size)
                folder = self.storage._mega_remote_join(
                    self.storage._mega_root(), "_staging", "material-jobs", str(job_id)
                )
                return "mega", self.storage._mega_upload_file(source, folder, name), ""
            except Exception as exc:
                if not (is_mega_capacity_full_error(exc) and self._mega_failover_ready()):
                    raise
                backend = "gdrive"
        if backend == "gdrive":
            return "gdrive", self._gdrive_upload_staging(source, job_id, name), ""

        paths = self.paths_provider()
        local_dir = Path(paths.tmp_dir) / "material-job-staging" / str(job_id)
        local_dir.mkdir(parents=True, exist_ok=True)
        local_path = local_dir / name
        shutil.copy2(source, local_path)
        return "local", "", str(local_path)

    def download(self, job: dict, target: Path):
        backend = str(job.get("stagingBackend") or job.get("staging_backend") or "local").lower()
        key = str(job.get("stagingKey") or job.get("staging_key") or "")
        local_path = str(job.get("stagingPath") or job.get("staging_path") or "")
        target = Path(target)
        if backend == "r2":
            if not key:
                raise RuntimeError("Shared Staging 缺少 R2 object key。")
            target.parent.mkdir(parents=True, exist_ok=True)
            providers.r2_client().download_file(providers.R2_BUCKET_NAME, key, str(target))
            return target
        if backend == "mega":
            if not key:
                raise RuntimeError("Shared Staging 缺少 MEGA object key。")
            return WebStorageRuntime(
                self.paths_provider(), storage_adapter=self.storage
            ).mega_download_file(key, target)
        if backend == "gdrive":
            if not key:
                raise RuntimeError("Shared Staging 缺少 Google Drive object key。")
            target.parent.mkdir(parents=True, exist_ok=True)
            session = providers.gdrive_authorized_session()
            try:
                with session.get(
                    f"https://www.googleapis.com/drive/v3/files/{key}?alt=media",
                    stream=True,
                    timeout=120,
                ) as response:
                    response.raise_for_status()
                    with target.open("wb") as handle:
                        for chunk in response.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                handle.write(chunk)
            finally:
                session.close()
            return target
        path = Path(local_path)
        if not path.is_file():
            raise RuntimeError("本機開發 Shared Staging 原始檔不存在。")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        return target

    def exists(self, job: dict) -> bool:
        backend = str(job.get("stagingBackend") or job.get("staging_backend") or "local").lower()
        key = str(job.get("stagingKey") or job.get("staging_key") or "")
        try:
            if backend == "r2":
                providers.r2_client().head_object(Bucket=providers.R2_BUCKET_NAME, Key=key)
                return bool(key)
            if backend == "mega":
                return bool(
                    key
                    and self.storage._mega_run(
                        ["mega-ls", key], check=False, timeout=60
                    ).returncode
                    == 0
                )
            if backend == "gdrive":
                return bool(
                    key
                    and providers.gdrive_service()
                    .files()
                    .get(fileId=key, fields="id,trashed")
                    .execute()
                    .get("id")
                )
            return Path(job.get("stagingPath") or job.get("staging_path") or "").is_file()
        except Exception:
            return False

    def delete(self, job: dict) -> None:
        backend = str(job.get("stagingBackend") or job.get("staging_backend") or "local").lower()
        key = str(job.get("stagingKey") or job.get("staging_key") or "")
        local_path = Path(job.get("stagingPath") or job.get("staging_path") or "")
        if backend == "local":
            if local_path.exists():
                shutil.rmtree(local_path.parent)
            return
        if not key:
            return
        if backend == "r2":
            providers.r2_delete_object(key)
            r2_ledger.record_deleted(key)
            return
        if backend == "mega":
            providers.mega_delete_object(
                key,
                is_configured=self.storage.mega_is_configured,
                run=self.storage._mega_run,
            )
            return
        if backend == "gdrive":
            providers.gdrive_delete_file(key)
            return
        raise RuntimeError(f"未知儲存後端：{backend}")


__all__ = ["MaterialStagingRuntime"]
