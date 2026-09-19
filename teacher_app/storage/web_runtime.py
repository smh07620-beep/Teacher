"""Canonical high-level storage reads used by the web application.

Credential and SDK/session ownership remains in :mod:`teacher_app.storage.providers`.
MEGAcmd process/session semantics are shared with the standalone worker adapter.
This module owns only HTTP-facing read/proxy/presign/cache composition so route
modules do not need callbacks from ``teacher_app.legacy_host``.
"""
from __future__ import annotations

import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import quote

from flask import Response, abort, jsonify, request, send_file, stream_with_context

from teacher_app.config import material_preview_cache_mb, material_preview_cache_ttl_seconds
from teacher_app.materials import storage as material_storage
from teacher_app.storage import providers
from teacher_app.storage.runtime import build_delete_adapters
from teacher_app.storage.worker_runtime import WorkerMaterialStorageAdapter


_PREVIEW_CACHE_LOCKS: dict[str, threading.RLock] = {}
_PREVIEW_CACHE_LOCKS_GUARD = threading.Lock()


def mega_web_status(exc) -> int:
    text = str(exc or "").lower()
    return 504 if ("逾時" in text or "timeout" in text) else 502


class WebStorageRuntime:
    """HTTP-facing storage runtime backed only by canonical provider owners."""

    def __init__(self, paths, *, storage_adapter=None):
        self.paths = paths
        self.storage = storage_adapter or WorkerMaterialStorageAdapter()

    def active_backend(self) -> str:
        return self.storage.active_backend()

    def mega_is_configured(self) -> bool:
        return self.storage.mega_is_configured()

    def mega_remote_join(self, *parts) -> str:
        return self.storage._mega_remote_join(*parts)

    def mega_root(self) -> str:
        return self.storage._mega_root()

    def mega_download_file(self, file_id: str, target: Path, *, timeout_seconds=None, retry_auth=True) -> Path:
        deadline = time.monotonic() + float(
            timeout_seconds if timeout_seconds is not None else providers.MEGA_WEB_READ_TIMEOUT_SECONDS
        )
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        tempdir = target.parent / f".mega-get-{uuid.uuid4().hex[:8]}"
        tempdir.mkdir(parents=True, exist_ok=True)
        try:
            providers.mega_login_if_needed(
                is_configured=self.storage.mega_is_configured,
                run=self.storage._mega_run,
                deadline=deadline,
            )
            try:
                self.storage._mega_run(
                    ["mega-get", str(file_id), str(tempdir)],
                    timeout=providers.mega_timeout_for_deadline(
                        deadline, max(providers.MEGACMD_TIMEOUT_SECONDS, 600)
                    ),
                )
            except RuntimeError:
                providers.invalidate_mega_auth_cache()
                if not retry_auth:
                    raise
                providers.mega_login_if_needed(
                    is_configured=self.storage.mega_is_configured,
                    run=self.storage._mega_run,
                    force=True,
                    deadline=deadline,
                )
                self.storage._mega_run(
                    ["mega-get", str(file_id), str(tempdir)],
                    timeout=providers.mega_timeout_for_deadline(
                        deadline, max(providers.MEGACMD_TIMEOUT_SECONDS, 600)
                    ),
                )
            files = [item for item in tempdir.iterdir() if item.is_file()]
            if not files:
                raise RuntimeError(f"MEGA 下載完成但找不到檔案：{file_id}")
            shutil.move(str(files[0]), str(target))
            return target
        finally:
            shutil.rmtree(tempdir, ignore_errors=True)

    def mega_send_file(self, file_id: str, filename: str, *, inline=True):
        temp_root = Path(self.paths.tmp_dir) / f"mega-read-{uuid.uuid4().hex[:10]}"
        temp_root.mkdir(parents=True, exist_ok=True)
        target = temp_root / (Path(filename).name or "file.bin")
        try:
            self.mega_download_file(
                file_id,
                target,
                timeout_seconds=providers.MEGA_WEB_READ_TIMEOUT_SECONDS,
            )
        except Exception:
            shutil.rmtree(temp_root, ignore_errors=True)
            raise
        response = send_file(
            target,
            as_attachment=not inline,
            download_name=filename,
            conditional=True,
        )
        response.call_on_close(lambda: shutil.rmtree(temp_root, ignore_errors=True))
        return response

    @staticmethod
    def _preview_cache_lock(cache_name: str):
        with _PREVIEW_CACHE_LOCKS_GUARD:
            lock = _PREVIEW_CACHE_LOCKS.get(cache_name)
            if lock is None:
                lock = threading.RLock()
                _PREVIEW_CACHE_LOCKS[cache_name] = lock
            return lock

    def _preview_cache_cleanup(self, *, protect: Path | None = None) -> None:
        try:
            directory = Path(self.paths.preview_cache_dir)
            directory.mkdir(parents=True, exist_ok=True)
            now = time.time()
            files = [path for path in directory.glob("*.pdf") if path.is_file()]
            protected = protect.resolve() if protect else None
            ttl = material_preview_cache_ttl_seconds()
            for path in list(files):
                if protected and path.resolve() == protected:
                    continue
                if now - path.stat().st_mtime > ttl:
                    try:
                        path.unlink()
                    except OSError:
                        pass
            files = [path for path in directory.glob("*.pdf") if path.is_file()]
            limit = material_preview_cache_mb() * 1024 * 1024
            total = sum(path.stat().st_size for path in files)
            if total <= limit:
                return
            for path in sorted(files, key=lambda item: item.stat().st_mtime):
                if total <= limit:
                    break
                if protected and path.resolve() == protected:
                    continue
                try:
                    size = path.stat().st_size
                    path.unlink()
                    total -= size
                except OSError:
                    pass
        except Exception:
            pass

    def mega_cached_preview(self, entry) -> Path:
        meta = entry.get("storageMeta") or {}
        preview_id = meta.get("previewFileId", "")
        if not preview_id:
            raise RuntimeError("MEGA 教材缺少單一預覽檔路徑。")
        cache_name = re.sub(
            r"[^A-Za-z0-9_-]",
            "_",
            str(entry.get("id") or "material"),
        ) + ".pdf"
        target = Path(self.paths.preview_cache_dir) / cache_name
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._preview_cache_lock(cache_name):
            valid = target.exists() and target.stat().st_size > 0
            if not valid:
                temp = target.with_suffix(".part")
                try:
                    temp.unlink(missing_ok=True)
                    self.mega_download_file(
                        preview_id,
                        temp,
                        timeout_seconds=providers.MEGA_WEB_READ_TIMEOUT_SECONDS,
                    )
                    os.replace(temp, target)
                finally:
                    temp.unlink(missing_ok=True)
            try:
                os.utime(target, None)
            except OSError:
                pass
            self._preview_cache_cleanup(protect=target)
        return target

    @staticmethod
    def gdrive_find_file_in_folder(folder_id: str, filename: str) -> str:
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
    def gdrive_proxy_file(file_id: str, filename: str, *, inline=True):
        if not file_id:
            abort(404)
        session = providers.gdrive_authorized_session()
        headers = {}
        range_header = request.headers.get("Range")
        if range_header:
            headers["Range"] = range_header
        upstream = session.get(
            f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media",
            headers=headers,
            stream=True,
            timeout=90,
        )
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
            params["ResponseContentDisposition"] = (
                f'{"inline" if inline else "attachment"}; filename="{safe}"'
            )
        return client.generate_presigned_url("get_object", Params=params, ExpiresIn=expires)

    def oci_presigned_get(self, key: str, *, download_name=None, inline=True) -> str:
        return self._presigned_get(
            providers.oci_client(),
            providers.OCI_BUCKET_NAME,
            key,
            str(download_name or ""),
            inline=inline,
            expires=providers.OCI_PRESIGN_SECONDS,
        )

    def r2_presigned_get(self, key: str, *, download_name=None, inline=True) -> str:
        return self._presigned_get(
            providers.r2_client(),
            providers.R2_BUCKET_NAME,
            key,
            str(download_name or ""),
            inline=inline,
            expires=providers.R2_PRESIGN_SECONDS,
        )

    def _mega_delete_object(self, value) -> None:
        providers.mega_delete_object(
            str(value),
            is_configured=self.storage.mega_is_configured,
            run=self.storage._mega_run,
        )

    @staticmethod
    def _gdrive_delete_material(entry) -> None:
        data = dict(entry or {})
        meta = data.get("storageMeta") or {}
        folder_id = meta.get("materialFolderId", "")
        if folder_id:
            providers.gdrive_delete_file(str(folder_id))
            return
        ids = [data.get("storageKey", ""), *(meta.get("slideFiles") or {}).values()]
        for file_id in dict.fromkeys(str(value) for value in ids if value):
            providers.gdrive_delete_file(file_id)

    @staticmethod
    def _oci_delete_prefix(prefix) -> None:
        material_storage.delete_prefix(
            providers.oci_client(),
            providers.OCI_BUCKET_NAME,
            str(prefix),
        )

    @staticmethod
    def _r2_delete_prefix(prefix) -> None:
        material_storage.delete_prefix(
            providers.r2_client(),
            providers.R2_BUCKET_NAME,
            str(prefix),
        )

    def delete_adapters(
        self,
        *,
        local_delete_object=None,
        local_delete_prefix=None,
        local_delete_material=None,
    ):
        """Compose strict deletion adapters around canonical provider owners."""
        return build_delete_adapters(
            mega_is_configured=self.storage.mega_is_configured,
            mega_delete_object=self._mega_delete_object,
            gdrive_is_configured=providers.gdrive_is_configured,
            gdrive_delete_object=lambda value: providers.gdrive_delete_file(str(value)),
            gdrive_delete_material=self._gdrive_delete_material,
            oci_is_configured=providers.oci_is_configured,
            oci_delete_object=lambda value: providers.oci_delete_object(str(value)),
            oci_delete_prefix=self._oci_delete_prefix,
            r2_is_configured=providers.r2_is_configured,
            r2_delete_object=lambda value: providers.r2_delete_object(str(value)),
            r2_delete_prefix=self._r2_delete_prefix,
            local_delete_object=local_delete_object,
            local_delete_prefix=local_delete_prefix,
            local_delete_material=local_delete_material,
        )


__all__ = ["WebStorageRuntime", "mega_web_status"]
