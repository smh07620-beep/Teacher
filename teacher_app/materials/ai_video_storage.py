"""Shared durable provider transport for worker-produced MP4 artifacts."""
from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from typing import Any

from teacher_app.config import storage_paths
from teacher_app.storage import providers, r2_ledger
from teacher_app.storage.worker_runtime import WorkerMaterialStorageAdapter
from teacher_app.storage.web_runtime import WebStorageRuntime

from teacher_app.materials.ai_video_repository import MP4_MIME


def _local_allowed() -> bool:
    return str(os.environ.get("AI_VIDEO_ALLOW_LOCAL_STORAGE", "false")).lower() in {"1", "true", "yes", "on"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class VideoStorage:
    """Same durable provider choice as presentation artifacts; local is fail-closed."""
    def __init__(self, *, paths_provider=storage_paths, storage_adapter=None):
        self.paths_provider = paths_provider
        self.storage = storage_adapter or WorkerMaterialStorageAdapter()

    def backend(self) -> str:
        requested = str(os.environ.get("AI_VIDEO_STORAGE_BACKEND") or os.environ.get("AI_PRESENTATION_STORAGE_BACKEND") or "auto").strip().lower()
        checks = {"r2": providers.r2_is_configured, "oci": providers.oci_is_configured, "gdrive": providers.gdrive_is_configured, "mega": self.storage.mega_is_configured}
        if requested in checks:
            if not checks[requested](): raise RuntimeError(f"AI 影片儲存設為 {requested}，但 provider 尚未完成設定。")
            return requested
        if requested == "local":
            if not _local_allowed(): raise RuntimeError("AI 影片本機儲存預設停用；單機開發請明確設定 AI_VIDEO_ALLOW_LOCAL_STORAGE=true。")
            return "local"
        if requested != "auto": raise RuntimeError("AI_VIDEO_STORAGE_BACKEND 必須是 auto、r2、oci、gdrive、mega 或 local。")
        for name in ("r2", "oci", "gdrive", "mega"):
            if checks[name](): return name
        if _local_allowed(): return "local"
        raise RuntimeError("AI 影片需要 Web 與 AI Worker 共用的 R2、OCI、Google Drive 或 MEGA。")

    def capability(self) -> dict[str, Any]:
        try:
            backend = self.backend(); return {"available": True, "backend": backend, "shared": backend != "local"}
        except Exception as exc:
            return {"available": False, "backend": "", "shared": False, "reason": str(exc)[:220]}

    def _local_root(self) -> Path:
        path = Path(self.paths_provider().tmp_dir) / "ai-videos"; path.mkdir(parents=True, exist_ok=True); return path

    def store(self, path: Path, *, job_id: str, filename: str) -> dict[str, Any]:
        path = Path(path)
        if not path.is_file() or path.stat().st_size <= 1024: raise RuntimeError("AI 影片輸出不存在或過小。")
        filename = Path(str(filename or "presentation.mp4")).name[:120]
        if not filename.lower().endswith(".mp4"): filename = Path(filename).stem + ".mp4"
        backend, size, digest = self.backend(), int(path.stat().st_size), sha256_file(path)
        if backend in {"r2", "oci"}:
            key = f"ai-videos/artifacts/{job_id}/{filename}"; client = providers.r2_client() if backend == "r2" else providers.oci_client(); bucket = providers.R2_BUCKET_NAME if backend == "r2" else providers.OCI_BUCKET_NAME
            client.upload_file(str(path), bucket, key, ExtraArgs={"ContentType": MP4_MIME})
            if backend == "r2": r2_ledger.record_object(key, size, is_staging=False)
        elif backend == "gdrive":
            uploaded = self.storage._gdrive_upload_file(providers.gdrive_service(), path, f"ai-video-{job_id}-{filename}"[:180], providers.GDRIVE_FOLDER_ID, {"smh_kind": "ai_video", "smh_job_id": job_id})
            key = str(uploaded["id"])
        elif backend == "mega":
            self.storage._mega_free_guard(size); folder = self.storage._mega_remote_join(self.storage._mega_root(), "ai-videos", "artifacts", job_id); key = self.storage._mega_upload_file(path, folder, filename)
        else:
            destination = self._local_root() / "artifacts" / job_id / filename; destination.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, destination); key = destination.relative_to(self._local_root()).as_posix()
        return {"backend": backend, "key": str(key), "filename": filename, "sha256": digest, "byteSize": size, "mimeType": MP4_MIME}

    def browser_response(self, location: dict[str, Any], *, download_name: str):
        backend, key = str(location.get("artifactBackend") or location.get("backend") or "").lower(), str(location.get("artifactStorageKey") or location.get("key") or "")
        if not key: raise RuntimeError("AI 影片儲存位置缺少 provider key。")
        web = WebStorageRuntime(self.paths_provider(), storage_adapter=self.storage)
        if backend == "r2": return web.r2_presigned_get(key, download_name=download_name, inline=True)
        if backend == "oci": return web.oci_presigned_get(key, download_name=download_name, inline=True)
        if backend == "gdrive": return web.gdrive_proxy_file(key, download_name, inline=True)
        if backend == "mega": return web.mega_send_file(key, download_name, inline=True)
        if backend == "local" and _local_allowed(): return self._local_root() / key
        raise RuntimeError("正式環境不允許讀取 AI 影片本機 artifact。")


__all__ = ["VideoStorage", "sha256_file"]
