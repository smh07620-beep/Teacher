"""Canonical storage/runtime behavior for PGY assessment templates.

Provider credentials and SDK/session construction remain owned by
``teacher_app.storage.providers``.  This module only composes those providers
for the small PGY-template lifecycle: validate, store, serve, and delete.
"""
from __future__ import annotations

import mimetypes
import os
import shutil
import time
import uuid
from pathlib import Path
from urllib.parse import quote

from flask import Response, abort, jsonify, redirect, request, send_file, stream_with_context

from teacher_app.materials import templates as material_templates
from teacher_app.storage import providers
from teacher_app.storage.runtime import build_delete_adapters
from teacher_app.storage.service import DeleteOutcome, DeleteRequest, delete_best_effort, delete_strict
from teacher_app.storage.worker_runtime import WorkerMaterialStorageAdapter

try:
    import pymupdf
except ImportError:  # pragma: no cover - optional deployment dependency
    pymupdf = None


def max_template_mb() -> int:
    try:
        value = int(os.environ.get("MAX_PGY_TEMPLATE_MB", "20"))
    except (TypeError, ValueError):
        value = 20
    return max(1, min(50, value))


def _content_type(path_or_name) -> str:
    return mimetypes.guess_type(str(path_or_name))[0] or "application/octet-stream"


def _is_mega_capacity_full_error(exc) -> bool:
    text = str(exc or "").lower()
    return any(
        marker in text
        for marker in (
            "免費模式已鎖定",
            "超過網站硬上限",
            "storage full",
            "storage is full",
            "quota exceeded",
            "over quota",
            "overquota",
            "insufficient storage",
            "not enough storage",
            "out of storage",
            "storage quota",
        )
    )


class PgyTemplateRuntime:
    def __init__(self, paths, *, storage_adapter=None):
        self.paths = paths
        self.storage = storage_adapter or WorkerMaterialStorageAdapter()

    def validate(self, path: Path, ext: str) -> dict:
        return material_templates.validate_template_file(
            Path(path),
            str(ext or "").lower(),
            max_template_mb(),
            pymupdf=pymupdf,
        )

    def _gdrive_find_file_in_folder(self, folder_id: str, filename: str) -> str:
        if not folder_id:
            return ""
        safe_name = str(filename).replace("\\", "\\\\").replace("'", "\\'")
        safe_parent = str(folder_id).replace("\\", "\\\\").replace("'", "\\'")
        query = f"'{safe_parent}' in parents and name = '{safe_name}' and trashed = false"
        result = providers.gdrive_service().files().list(
            q=query,
            fields="files(id,name)",
            pageSize=2,
        ).execute()
        files = result.get("files", [])
        return files[0]["id"] if files else ""

    @staticmethod
    def _gdrive_create_folder(name: str, parent_id: str) -> str:
        body = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        return providers.gdrive_service().files().create(
            body=body,
            fields="id,name",
        ).execute()["id"]

    @staticmethod
    def _gdrive_upload_file(local_path: Path, name: str, parent_id: str) -> str:
        media = providers.gdrive_media_file_upload(
            local_path,
            mimetype=_content_type(local_path),
            chunk_mb=providers.GDRIVE_CHUNK_MB,
        )
        result = providers.gdrive_service().files().create(
            body={"name": name, "parents": [parent_id]},
            media_body=media,
            fields="id,name,size,mimeType",
        ).execute()
        return str(result["id"])

    def _oci_free_guard(self, extra_bytes: int) -> None:
        if not bool(getattr(self.storage, "free_only", True)):
            return
        client = providers.oci_client()
        used = 0
        token = None
        while True:
            params = {"Bucket": providers.OCI_BUCKET_NAME}
            if token:
                params["ContinuationToken"] = token
            result = client.list_objects_v2(**params)
            used += sum(int(item.get("Size", 0) or 0) for item in result.get("Contents", []))
            if not result.get("IsTruncated"):
                break
            token = result.get("NextContinuationToken")
            if not token:
                break
        limit = int(providers.OCI_FREE_LIMIT_GB * 1024**3)
        if used + int(extra_bytes or 0) > limit:
            raise RuntimeError(
                f"免費模式已鎖定：Oracle 教材空間約 {used/1024**3:.2f}GB，"
                f"新增此檔會超過網站設定的 {providers.OCI_FREE_LIMIT_GB:.1f}GB 上限。請先刪除舊教材。"
            )

    def _store_with_backend(self, backend: str, local_path: Path, template_type: str, filename: str) -> str:
        local_path = Path(local_path)
        suffix = local_path.suffix.lower()
        if backend == "mega":
            self.storage._mega_free_guard(local_path.stat().st_size)
            folder = self.storage._mega_remote_join(
                self.storage._mega_root(),
                "pgy-assessment-templates",
            )
            self.storage._mega_ensure_dir(folder)
            return self.storage._mega_upload_file(
                local_path,
                folder,
                f"{template_type}-{uuid.uuid4().hex[:8]}{suffix}",
            )
        if backend == "gdrive":
            parent = self._gdrive_find_file_in_folder(
                providers.GDRIVE_FOLDER_ID,
                "pgy-assessment-templates",
            ) or self._gdrive_create_folder(
                "pgy-assessment-templates",
                providers.GDRIVE_FOLDER_ID,
            )
            return self._gdrive_upload_file(
                local_path,
                f"{template_type}-{uuid.uuid4().hex[:8]}{suffix}",
                parent,
            )
        key = f"pgy_assessment_templates/{template_type}/{uuid.uuid4().hex}{suffix}"
        if backend == "oci":
            self._oci_free_guard(local_path.stat().st_size)
            providers.oci_client().upload_file(
                str(local_path),
                providers.OCI_BUCKET_NAME,
                key,
                ExtraArgs={"ContentType": _content_type(filename)},
            )
            return key
        if backend == "r2":
            providers.r2_client().upload_file(
                str(local_path),
                providers.R2_BUCKET_NAME,
                key,
                ExtraArgs={"ContentType": _content_type(filename)},
            )
            return key

        destination_dir = Path(self.paths.pgy_assessment_templates_dir)
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / f"{template_type}-{uuid.uuid4().hex[:8]}{suffix}"
        shutil.copy2(local_path, destination)
        return str(destination)

    def store(self, local_path: Path, template_type: str, filename: str) -> tuple[str, str]:
        backend = self.storage.active_backend()
        try:
            return backend, self._store_with_backend(backend, Path(local_path), template_type, filename)
        except Exception as exc:
            fallback = ""
            if backend == "mega" and _is_mega_capacity_full_error(exc):
                enabled = os.environ.get("STORAGE_FAILOVER_ON_FULL", "false").strip().lower() in {
                    "1",
                    "true",
                    "yes",
                    "on",
                }
                requested = os.environ.get("STORAGE_FALLBACK_BACKEND", "").strip().lower()
                if enabled and requested == "gdrive" and providers.gdrive_is_configured():
                    fallback = "gdrive"
            if fallback:
                return fallback, self._store_with_backend(fallback, Path(local_path), template_type, filename)
            raise

    def _delete_adapters(self):
        return build_delete_adapters(
            mega_is_configured=self.storage.mega_is_configured,
            mega_delete_object=lambda key: providers.mega_delete_object(
                str(key),
                is_configured=self.storage.mega_is_configured,
                run=self.storage._mega_run,
            ),
            gdrive_is_configured=providers.gdrive_is_configured,
            gdrive_delete_object=lambda key: providers.gdrive_delete_file(str(key)),
            oci_is_configured=providers.oci_is_configured,
            oci_delete_object=lambda key: providers.oci_delete_object(str(key)),
            r2_is_configured=providers.r2_is_configured,
            r2_delete_object=lambda key: providers.r2_delete_object(str(key)),
            local_delete_object=lambda path: Path(path).unlink(missing_ok=True),
        )

    def delete(self, row, *, best_effort: bool = True):
        if not row:
            return DeleteOutcome("local", "object", True)
        data = dict(row)
        backend = str(data.get("storage_backend") or "local").lower()
        key = str(data.get("storage_key") or "")
        payload = Path(key) if backend == "local" and key else key
        if not payload:
            return DeleteOutcome(backend, "object", True)
        delete_request = DeleteRequest(backend, "object", payload)
        if best_effort:
            return delete_best_effort(delete_request, self._delete_adapters())
        return delete_strict(delete_request, self._delete_adapters())

    def _mega_download(self, file_id: str, target: Path) -> Path:
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        download_dir = target.parent / f".mega-get-{uuid.uuid4().hex[:8]}"
        download_dir.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + float(providers.MEGA_WEB_READ_TIMEOUT_SECONDS)
        try:
            providers.mega_login_if_needed(
                is_configured=self.storage.mega_is_configured,
                run=self.storage._mega_run,
                deadline=deadline,
            )
            try:
                self.storage._mega_run(
                    ["mega-get", str(file_id), str(download_dir)],
                    timeout=providers.mega_timeout_for_deadline(
                        deadline,
                        max(providers.MEGACMD_TIMEOUT_SECONDS, 600),
                    ),
                )
            except RuntimeError:
                providers.invalidate_mega_auth_cache()
                providers.mega_login_if_needed(
                    is_configured=self.storage.mega_is_configured,
                    run=self.storage._mega_run,
                    force=True,
                    deadline=deadline,
                )
                self.storage._mega_run(
                    ["mega-get", str(file_id), str(download_dir)],
                    timeout=providers.mega_timeout_for_deadline(
                        deadline,
                        max(providers.MEGACMD_TIMEOUT_SECONDS, 600),
                    ),
                )
            files = [item for item in download_dir.iterdir() if item.is_file()]
            if not files:
                raise RuntimeError(f"MEGA 下載完成但找不到檔案：{file_id}")
            shutil.move(str(files[0]), str(target))
            return target
        finally:
            shutil.rmtree(download_dir, ignore_errors=True)

    def _send_mega(self, key: str, filename: str, *, inline: bool):
        root = Path(self.paths.tmp_dir) / f"pgy-template-read-{uuid.uuid4().hex[:10]}"
        root.mkdir(parents=True, exist_ok=True)
        target = root / (Path(filename).name or "file.bin")
        try:
            self._mega_download(key, target)
        except Exception:
            shutil.rmtree(root, ignore_errors=True)
            raise
        response = send_file(
            target,
            as_attachment=not inline,
            download_name=filename,
            conditional=True,
        )
        response.call_on_close(lambda: shutil.rmtree(root, ignore_errors=True))
        return response

    @staticmethod
    def _send_gdrive(key: str, filename: str, *, inline: bool):
        if not key:
            abort(404)
        session = providers.gdrive_authorized_session()
        headers = {}
        range_header = request.headers.get("Range")
        if range_header:
            headers["Range"] = range_header
        url = f"https://www.googleapis.com/drive/v3/files/{key}?alt=media"
        upstream = session.get(url, headers=headers, stream=True, timeout=90)
        if upstream.status_code not in (200, 206):
            message = upstream.text[:500]
            upstream.close()
            session.close()
            return jsonify({
                "error": f"Google Drive 讀取失敗（HTTP {upstream.status_code}）：{message}"
            }), 502

        output_headers = {}
        for name in (
            "Content-Type",
            "Content-Length",
            "Content-Range",
            "Accept-Ranges",
            "ETag",
            "Last-Modified",
        ):
            if upstream.headers.get(name):
                output_headers[name] = upstream.headers[name]
        disposition = "inline" if inline else "attachment"
        safe = Path(filename or "download").name.replace('"', "'").replace("\r", "").replace("\n", "")
        ascii_name = safe.encode("ascii", "ignore").decode("ascii").strip() or "download"
        output_headers["Content-Disposition"] = (
            f'{disposition}; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(safe)}'
        )
        output_headers["Cache-Control"] = "private, max-age=300"
        response = Response(
            stream_with_context(upstream.iter_content(chunk_size=512 * 1024)),
            status=upstream.status_code,
            headers=output_headers,
            direct_passthrough=True,
        )
        response.call_on_close(upstream.close)
        response.call_on_close(session.close)
        return response

    @staticmethod
    def _presigned_get(client, bucket: str, key: str, filename: str, *, inline: bool, expires: int) -> str:
        params = {"Bucket": bucket, "Key": key}
        if filename:
            safe = str(filename).replace('"', "'").replace("\r", "").replace("\n", "")
            disposition = "inline" if inline else "attachment"
            params["ResponseContentDisposition"] = f'{disposition}; filename="{safe}"'
        return client.generate_presigned_url("get_object", Params=params, ExpiresIn=expires)

    def send(self, row, *, inline: bool = True):
        data = dict(row)
        backend = str(data.get("storage_backend") or "local").lower()
        key = str(data.get("storage_key") or "")
        filename = str(data.get("filename") or "download")
        if backend == "mega":
            return self._send_mega(key, filename, inline=inline)
        if backend == "gdrive":
            return self._send_gdrive(key, filename, inline=inline)
        if backend == "oci":
            url = self._presigned_get(
                providers.oci_client(),
                providers.OCI_BUCKET_NAME,
                key,
                filename,
                inline=inline,
                expires=providers.OCI_PRESIGN_SECONDS,
            )
            return redirect(url, code=302)
        if backend == "r2":
            url = self._presigned_get(
                providers.r2_client(),
                providers.R2_BUCKET_NAME,
                key,
                filename,
                inline=inline,
                expires=providers.R2_PRESIGN_SECONDS,
            )
            return redirect(url, code=302)
        path = Path(key)
        if not path.exists():
            abort(404)
        return send_file(path, as_attachment=not inline, download_name=filename)


__all__ = ["PgyTemplateRuntime", "max_template_mb"]
