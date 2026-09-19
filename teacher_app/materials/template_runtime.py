"""Canonical provider/runtime composition for document export templates."""
from __future__ import annotations

import mimetypes
import os
import shutil
import uuid
from pathlib import Path
from typing import Callable

from teacher_app.materials import storage as material_storage
from teacher_app.materials import templates
from teacher_app.storage import providers
from teacher_app.storage.service import DeleteOutcome, DeleteRequest, delete_best_effort, delete_strict
from teacher_app.storage.web_runtime import WebStorageRuntime
from teacher_app.storage.worker_runtime import WorkerMaterialStorageAdapter

try:
    import pymupdf
except ImportError:  # pragma: no cover - optional deployment dependency
    pymupdf = None


DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def max_doc_template_mb() -> int:
    try:
        value = int(os.environ.get("MAX_DOC_TEMPLATE_MB", "20"))
    except (TypeError, ValueError):
        value = 20
    return max(1, min(50, value))


def _content_type(path_or_name) -> str:
    return mimetypes.guess_type(str(path_or_name))[0] or "application/octet-stream"


class DocumentTemplateRuntime:
    """Store, serve and delete group Word templates using canonical providers.

    R2 usage-ledger ownership has not moved into the storage package yet.  The
    upload accounting callback is deliberately narrow so production can preserve
    the existing ledger write without importing the legacy host or duplicating SQL.
    """

    def __init__(
        self,
        paths,
        *,
        storage_adapter=None,
        web_runtime=None,
        r2_record_object: Callable[[str, int], None] | None = None,
    ):
        self.paths = paths
        self.storage = storage_adapter or WorkerMaterialStorageAdapter()
        self.web = web_runtime or WebStorageRuntime(paths, storage_adapter=self.storage)
        self.r2_record_object = r2_record_object

    def validate(self, path: Path, ext: str) -> dict:
        return templates.validate_template_file(
            Path(path),
            str(ext or "").lower(),
            max_doc_template_mb(),
            pymupdf=pymupdf,
        )

    def active_backend(self) -> str:
        return self.storage.active_backend()

    def _oci_free_guard(self, extra_bytes: int) -> None:
        if not bool(getattr(self.storage, "free_only", True)):
            return
        used = material_storage.bucket_usage_bytes(
            providers.oci_client(),
            providers.OCI_BUCKET_NAME,
        )
        limit = int(providers.OCI_FREE_LIMIT_GB * 1024**3)
        if used + int(extra_bytes or 0) > limit:
            raise RuntimeError(
                f"免費模式已鎖定：Oracle 教材空間約 {used/1024**3:.2f}GB，"
                f"新增此檔會超過網站設定的 {providers.OCI_FREE_LIMIT_GB:.1f}GB 上限。請先刪除舊教材。"
            )

    def store(self, local_path: Path, group_key: str, storage_filename: str) -> tuple[str, str]:
        local_path = Path(local_path)
        backend = self.active_backend()
        if backend == "mega":
            self.storage._mega_free_guard(local_path.stat().st_size)
            folder = self.storage._mega_remote_join(self.storage._mega_root(), "doc-templates")
            self.storage._mega_ensure_dir(folder)
            key = self.storage._mega_upload_file(
                local_path,
                folder,
                f"word-template-{group_key}-{uuid.uuid4().hex[:8]}.docx",
            )
            return backend, key
        if backend == "oci":
            self._oci_free_guard(local_path.stat().st_size)
            key = f"doc_templates/{group_key}/{uuid.uuid4().hex}.docx"
            providers.oci_client().upload_file(
                str(local_path),
                providers.OCI_BUCKET_NAME,
                key,
                ExtraArgs={"ContentType": DOCX_CONTENT_TYPE},
            )
            return backend, key
        if backend == "gdrive":
            service = providers.gdrive_service()
            media = providers.gdrive_media_file_upload(
                local_path,
                mimetype=DOCX_CONTENT_TYPE,
                chunk_mb=providers.GDRIVE_CHUNK_MB,
            )
            uploaded = service.files().create(
                body={
                    "name": f"word-template-{group_key}.docx",
                    "parents": [providers.GDRIVE_FOLDER_ID],
                    "appProperties": {"smh_kind": "doc_template", "smh_group": group_key},
                },
                media_body=media,
                fields="id,name,size,mimeType",
            ).execute()
            return backend, str(uploaded["id"])
        if backend == "r2":
            if self.r2_record_object is None:
                raise RuntimeError("R2 使用量 ledger callback 尚未注入。")
            key = f"doc_templates/{group_key}/{uuid.uuid4().hex}.docx"
            providers.r2_client().upload_file(
                str(local_path),
                providers.R2_BUCKET_NAME,
                key,
                ExtraArgs={"ContentType": DOCX_CONTENT_TYPE},
            )
            self.r2_record_object(key, local_path.stat().st_size)
            return backend, key

        destination = Path(self.paths.doc_templates_dir) / storage_filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, destination)
        return "local", ""

    def configured(self, backend: str) -> bool:
        backend = str(backend or "local").lower()
        if backend == "mega":
            return self.storage.mega_is_configured()
        if backend == "gdrive":
            return providers.gdrive_is_configured()
        if backend == "oci":
            return providers.oci_is_configured()
        if backend == "r2":
            return providers.r2_is_configured()
        return True

    def send(self, row, *, inline: bool = True):
        data = dict(row)
        backend = str(data.get("storage_backend") or "local").lower()
        key = str(data.get("storage_key") or "")
        filename = str(data.get("filename") or "download")
        if backend == "mega":
            return self.web.mega_send_file(key, filename, inline=inline)
        if backend == "gdrive":
            return self.web.gdrive_proxy_file(key, filename, inline=inline)
        if backend == "oci":
            return self.web.oci_presigned_get(key, download_name=filename, inline=inline)
        if backend == "r2":
            return self.web.r2_presigned_get(key, download_name=filename, inline=inline)
        path = Path(self.paths.doc_templates_dir) / str(data.get("storage_filename") or "")
        return path

    def _delete_adapters(self):
        return self.web.delete_adapters(
            local_delete_object=lambda path: Path(path).unlink(missing_ok=True),
        )

    def delete(self, row, *, best_effort: bool):
        if not row:
            return DeleteOutcome("local", "object", True)
        data = dict(row)
        backend = str(data.get("storage_backend") or "local").lower()
        key = str(data.get("storage_key") or "")
        payload = (
            Path(self.paths.doc_templates_dir) / str(data.get("storage_filename") or "")
            if backend == "local"
            else key
        )
        if not payload:
            return DeleteOutcome(backend, "object", True)
        request = DeleteRequest(backend, "object", payload)
        adapters = self._delete_adapters()
        return (
            delete_best_effort(request, adapters)
            if best_effort
            else delete_strict(request, adapters)
        )


__all__ = ["DocumentTemplateRuntime", "max_doc_template_mb"]
