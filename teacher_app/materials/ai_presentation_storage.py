"""Durable provider transport for AI PowerPoint templates and generated artifacts."""
from __future__ import annotations

import hashlib
import os
import re
import shutil
from pathlib import Path
from typing import Any

from teacher_app.config import storage_paths
from teacher_app.storage import providers, r2_ledger
from teacher_app.storage.worker_runtime import WorkerMaterialStorageAdapter
from teacher_app.storage.web_runtime import WebStorageRuntime


PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
_BACKENDS = {"r2", "oci", "gdrive", "mega", "local"}


def _env_true(name: str, default: bool = False) -> bool:
    fallback = "true" if default else "false"
    return str(os.environ.get(name, fallback)).strip().lower() in {"1", "true", "yes", "on"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_filename(value: str, fallback: str = "presentation.pptx") -> str:
    name = Path(str(value or fallback).replace("\\", "/")).name
    name = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._ -]+", "-", name).strip(" .-") or fallback
    if not name.lower().endswith(".pptx"):
        name = Path(name).stem + ".pptx"
    return name[:120]


class PresentationStorage:
    """Shared store used by Web and the dedicated AI Worker.

    Local storage is fail-closed unless explicitly enabled for single-host
    development with ``AI_PRESENTATION_ALLOW_LOCAL_STORAGE=true``.
    """

    def __init__(self, *, paths_provider=storage_paths, storage_adapter=None):
        self.paths_provider = paths_provider
        self.storage = storage_adapter or WorkerMaterialStorageAdapter()

    @staticmethod
    def requested_backend() -> str:
        value = str(os.environ.get("AI_PRESENTATION_STORAGE_BACKEND") or "auto").strip().lower()
        if value not in {"auto", *_BACKENDS}:
            raise RuntimeError("AI_PRESENTATION_STORAGE_BACKEND 必須是 auto、r2、oci、gdrive、mega 或 local。")
        return value

    def backend(self) -> str:
        requested = self.requested_backend()
        checks = {
            "r2": providers.r2_is_configured,
            "oci": providers.oci_is_configured,
            "gdrive": providers.gdrive_is_configured,
            "mega": self.storage.mega_is_configured,
        }
        if requested in checks:
            if not checks[requested]():
                raise RuntimeError(f"AI PowerPoint 儲存設為 {requested}，但 provider 尚未完成設定。")
            return requested
        if requested == "local":
            if not _env_true("AI_PRESENTATION_ALLOW_LOCAL_STORAGE"):
                raise RuntimeError("AI PowerPoint 本機儲存預設停用；單機開發請明確設定 AI_PRESENTATION_ALLOW_LOCAL_STORAGE=true。")
            return "local"
        for candidate in ("r2", "oci", "gdrive", "mega"):
            if checks[candidate]():
                return candidate
        if _env_true("AI_PRESENTATION_ALLOW_LOCAL_STORAGE"):
            return "local"
        raise RuntimeError("AI PowerPoint 需要 Web 與 AI Worker 共用的 R2、OCI、Google Drive 或 MEGA。")

    def capability(self) -> dict[str, Any]:
        try:
            backend = self.backend()
            return {"available": True, "backend": backend, "shared": backend != "local", "localDevelopmentOnly": backend == "local"}
        except Exception as exc:
            return {"available": False, "backend": "", "shared": False, "localDevelopmentOnly": False, "reason": str(exc)[:220]}

    def _local_root(self) -> Path:
        root = Path(self.paths_provider().tmp_dir) / "ai-presentations"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _gdrive_upload(self, path: Path, namespace: str, object_id: str, filename: str) -> str:
        uploaded = self.storage._gdrive_upload_file(
            providers.gdrive_service(), path, f"{namespace}-{object_id}-{filename}"[:180],
            providers.GDRIVE_FOLDER_ID,
            {"smh_kind": "ai_presentation", "smh_namespace": namespace, "smh_object_id": object_id},
        )
        return str(uploaded["id"])

    def store(self, path: Path, *, namespace: str, object_id: str, filename: str) -> dict[str, Any]:
        path = Path(path)
        if not path.is_file() or path.stat().st_size <= 0:
            raise ValueError("PowerPoint 檔案不存在或空白。")
        backend, filename = self.backend(), safe_filename(filename)
        digest, byte_size = sha256_file(path), int(path.stat().st_size)
        if backend in {"r2", "oci"}:
            key = f"ai-presentations/{namespace}/{object_id}/{filename}"
            client = providers.r2_client() if backend == "r2" else providers.oci_client()
            bucket = providers.R2_BUCKET_NAME if backend == "r2" else providers.OCI_BUCKET_NAME
            client.upload_file(str(path), bucket, key, ExtraArgs={"ContentType": PPTX_MIME})
            if backend == "r2":
                r2_ledger.record_object(key, byte_size, is_staging=False)
        elif backend == "gdrive":
            key = self._gdrive_upload(path, namespace, object_id, filename)
        elif backend == "mega":
            self.storage._mega_free_guard(byte_size)
            folder = self.storage._mega_remote_join(self.storage._mega_root(), "ai-presentations", namespace, object_id)
            key = self.storage._mega_upload_file(path, folder, filename)
        else:
            relative = Path(namespace) / object_id / filename
            destination = self._local_root() / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            key = relative.as_posix()
        return {"backend": backend, "key": str(key), "filename": filename, "sha256": digest, "byteSize": byte_size, "mimeType": PPTX_MIME}

    def download(self, location: dict[str, Any], target: Path) -> Path:
        backend = str(location.get("backend") or location.get("storageBackend") or "local").lower()
        key = str(location.get("key") or location.get("storageKey") or "")
        if not key:
            raise RuntimeError("PowerPoint 儲存位置缺少 provider key。")
        target = Path(target); target.parent.mkdir(parents=True, exist_ok=True)
        if backend == "r2":
            providers.r2_client().download_file(providers.R2_BUCKET_NAME, key, str(target))
        elif backend == "oci":
            providers.oci_client().download_file(providers.OCI_BUCKET_NAME, key, str(target))
        elif backend == "gdrive":
            session = providers.gdrive_authorized_session()
            try:
                with session.get(f"https://www.googleapis.com/drive/v3/files/{key}?alt=media", stream=True, timeout=180) as response:
                    response.raise_for_status()
                    with target.open("wb") as handle:
                        for chunk in response.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                handle.write(chunk)
            finally:
                session.close()
        elif backend == "mega":
            WebStorageRuntime(self.paths_provider(), storage_adapter=self.storage).mega_download_file(key, target)
        elif backend == "local":
            if not _env_true("AI_PRESENTATION_ALLOW_LOCAL_STORAGE"):
                raise RuntimeError("正式環境不允許讀取 AI PowerPoint 本機 artifact。")
            source = self._local_root() / key
            if not source.is_file():
                raise RuntimeError("AI PowerPoint 本機 artifact 已不存在。")
            shutil.copy2(source, target)
        else:
            raise RuntimeError("未知的 AI PowerPoint 儲存 provider。")
        if not target.is_file() or target.stat().st_size <= 0:
            raise RuntimeError("AI PowerPoint provider 回傳空白檔案。")
        expected = str(location.get("sha256") or location.get("artifactSha256") or "")
        if expected and sha256_file(target) != expected:
            target.unlink(missing_ok=True)
            raise RuntimeError("AI PowerPoint artifact checksum 驗證失敗。")
        return target

    def browser_response(self, location: dict[str, Any], *, download_name: str):
        backend = str(location.get("backend") or location.get("artifactBackend") or "local").lower()
        key = str(location.get("key") or location.get("artifactStorageKey") or "")
        web = WebStorageRuntime(self.paths_provider(), storage_adapter=self.storage)
        if backend == "r2":
            return web.r2_presigned_get(key, download_name=download_name, inline=False)
        if backend == "oci":
            return web.oci_presigned_get(key, download_name=download_name, inline=False)
        if backend == "gdrive":
            return web.gdrive_proxy_file(key, download_name, inline=False)
        if backend == "mega":
            return web.mega_send_file(key, download_name, inline=False)
        if backend == "local":
            if not _env_true("AI_PRESENTATION_ALLOW_LOCAL_STORAGE"):
                raise RuntimeError("正式環境不允許下載 AI PowerPoint 本機 artifact。")
            return self._local_root() / key
        raise RuntimeError("未知的 AI PowerPoint 儲存 provider。")


__all__ = ["PPTX_MIME", "PresentationStorage", "safe_filename", "sha256_file"]
