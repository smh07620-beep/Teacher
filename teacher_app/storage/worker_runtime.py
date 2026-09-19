"""Flask-free storage/runtime adapter for the standalone material worker.

Provider credentials and SDK/session construction stay owned by
``teacher_app.storage.providers``.  This module only composes those canonical
providers with the local worker's conversion and upload workflow.
"""
from __future__ import annotations

import io
import mimetypes
import ntpath
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any

from teacher_app.storage import providers
from teacher_app.storage.service import StorageConfigurationError, StorageProviderAdapter, select_backend

try:
    import pymupdf
except ImportError:  # pragma: no cover - deployment dependency is optional at import time
    pymupdf = None

try:
    from PIL import Image
except ImportError:  # pragma: no cover - deployment dependency is optional at import time
    Image = None


OFFICE_EXT = frozenset({".pptx", ".ppt", ".doc", ".docx", ".xls", ".xlsx", ".odp", ".odt", ".ods"})
_CONVERSION_LOCK = threading.Lock()


def _env_true(name: str, default: bool) -> bool:
    fallback = "true" if default else "false"
    return os.environ.get(name, fallback).strip().lower() not in {"0", "false", "no", "off"}


class WorkerMaterialStorageAdapter:
    """Local-worker view of canonical storage providers.

    The adapter never creates credentials or an alternate provider session.
    Google Drive clients and the shared MEGAcmd auth cache come exclusively
    from :mod:`teacher_app.storage.providers`.
    """

    def __init__(self) -> None:
        self.requested_backend = os.environ.get("MATERIAL_STORAGE_BACKEND", "auto").strip().lower() or "auto"
        self.single_preview = _env_true("MATERIAL_SINGLE_PREVIEW", True)
        self.preview_optimize = _env_true("MATERIAL_PREVIEW_OPTIMIZE", True)
        self.pdf_linearize = _env_true("MATERIAL_PDF_LINEARIZE", True)
        self.free_only = _env_true("FREE_ONLY_MODE", True)
        self.slide_format_name = os.environ.get("MATERIAL_SLIDE_FORMAT", "webp").strip().lower()
        if self.slide_format_name not in {"webp", "png"}:
            self.slide_format_name = "webp"
        self.webp_quality = max(70, min(96, int(os.environ.get("MATERIAL_WEBP_QUALITY", "88"))))
        self.soffice = os.environ.get("SOFFICE_PATH", "soffice")

    # ------------------------------------------------------------------
    # Provider selection / MEGAcmd runtime
    # ------------------------------------------------------------------
    @staticmethod
    def _megacmd_path_module():
        return ntpath if sys.platform.startswith("win") else os.path

    def _megacmd_windows_dirs(self) -> list[str]:
        if not sys.platform.startswith("win"):
            return []
        path_module = self._megacmd_path_module()
        return [
            path_module.join(base, "MEGAcmd")
            for base in (
                os.environ.get("ProgramFiles", ""),
                os.environ.get("ProgramFiles(x86)", ""),
            )
            if base
        ]

    def _megacmd_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["HOME"] = providers.MEGACMD_HOME
        separator = ";" if sys.platform.startswith("win") else os.pathsep
        path_module = self._megacmd_path_module()
        current = [item for item in str(env.get("PATH", "")).split(separator) if item]
        known = {path_module.normcase(path_module.normpath(item)) for item in current}
        additions: list[str] = []
        for directory in self._megacmd_windows_dirs():
            normalized = path_module.normcase(path_module.normpath(directory))
            if normalized not in known:
                additions.append(directory)
                known.add(normalized)
        env["PATH"] = separator.join([*additions, *current])
        return env

    def _mega_find(self, command: str) -> str:
        command = str(command)
        candidates = [command]
        if sys.platform.startswith("win") and not os.path.splitext(command)[1]:
            candidates.extend(f"{command}{extension}" for extension in (".bat", ".cmd", ".exe"))
        path = self._megacmd_env().get("PATH", "")
        for candidate in candidates:
            resolved = shutil.which(candidate, path=path)
            if resolved:
                return resolved
        return ""

    def _mega_run(self, args, *, check: bool = True, timeout: int | None = None):
        cmd = [str(value) for value in args]
        if cmd:
            cmd[0] = self._mega_find(cmd[0]) or cmd[0]
        batch_wrapper = bool(
            cmd
            and sys.platform.startswith("win")
            and str(cmd[0]).lower().endswith((".bat", ".cmd"))
        )
        try:
            completed = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=self._megacmd_env(),
                timeout=timeout or providers.MEGACMD_TIMEOUT_SECONDS,
                check=False,
                shell=batch_wrapper,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("找不到官方 MEGAcmd 指令。請確認本機已安裝 MEGAcmd。") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"MEGAcmd 執行逾時：{' '.join(cmd[:1])}") from exc
        if check and completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "MEGAcmd command failed").strip()
            raise RuntimeError(f"MEGAcmd 執行失敗 ({Path(cmd[0]).name})：{detail[-600:]}")
        return completed

    def mega_is_configured(self) -> bool:
        return providers.mega_is_configured(self._mega_find)

    def _mega_login(self) -> None:
        providers.mega_login_if_needed(
            is_configured=self.mega_is_configured,
            run=self._mega_run,
        )

    @staticmethod
    def _mega_remote_join(*parts: object) -> str:
        cleaned = []
        for part in parts:
            text = str(part or "").replace("\\", "/").strip("/")
            if text:
                cleaned.append(text)
        return "/" + "/".join(cleaned)

    def _mega_ensure_dir(self, remote_path: str) -> str:
        self._mega_login()
        remote_path = str(remote_path or "").strip()
        if not remote_path:
            raise RuntimeError("MEGA 資料夾路徑不可為空。")
        completed = self._mega_run(["mega-mkdir", "-p", remote_path], check=False, timeout=60)
        if completed.returncode == 0:
            return remote_path
        detail = ((completed.stderr or "") + "\n" + (completed.stdout or "")).strip()
        normalized = detail.lower().replace(" ", "")
        if any(marker in normalized for marker in ("folderalreadyexists", "alreadyexists", "eexist")):
            return remote_path
        raise RuntimeError(f"MEGA 建立資料夾失敗：{detail[-600:] or 'unknown error'}")

    def _mega_root(self) -> str:
        self._mega_login()
        root = self._mega_remote_join(providers.MEGA_ROOT_FOLDER)
        return self._mega_ensure_dir(root)

    def _mega_storage_space(self) -> dict[str, int]:
        self._mega_login()
        completed = self._mega_run(["mega-df"], timeout=60)
        match = re.search(
            r"USED STORAGE:\s*([0-9]+)\s+[^\n]*?of\s+([0-9]+)",
            completed.stdout or "",
            re.I,
        )
        if match:
            return {"used": int(match.group(1)), "total": int(match.group(2))}
        line = next(
            (line for line in (completed.stdout or "").splitlines() if "USED STORAGE:" in line.upper()),
            "",
        )
        numbers = [int(value.replace(",", "")) for value in re.findall(r"[0-9][0-9,]*", line)]
        if len(numbers) >= 2:
            return {"used": numbers[0], "total": numbers[-1]}
        raise RuntimeError("無法解析 MEGAcmd mega-df 的容量資訊。")

    def _mega_free_guard(self, extra_bytes: int = 0) -> None:
        if not self.free_only:
            return
        info = self._mega_storage_space()
        configured = int(providers.MEGA_STORAGE_LIMIT_GB * 1024**3)
        account_cap = int(info["total"] * 0.98) if info["total"] else configured
        limit = min(configured, account_cap)
        if info["used"] + int(extra_bytes or 0) > limit:
            raise RuntimeError(
                f"免費模式已鎖定：MEGA 已使用約 {info['used']/1024**3:.2f}GB；"
                f"加入此檔會超過網站硬上限 {limit/1024**3:.2f}GB。請先刪除舊教材。"
            )

    def _mega_upload_file(self, local_path: Path, folder: str, remote_name: str) -> str:
        self._mega_login()
        folder = self._mega_ensure_dir(folder)
        remote_path = self._mega_remote_join(folder, remote_name)
        self._mega_run(["mega-rm", "-f", remote_path], check=False, timeout=60)
        self._mega_run(
            ["mega-put", "-c", str(local_path), folder],
            timeout=max(providers.MEGACMD_TIMEOUT_SECONDS, 600),
        )
        uploaded = self._mega_remote_join(folder, local_path.name)
        if local_path.name != remote_name:
            self._mega_run(["mega-mv", uploaded, remote_path], timeout=60)
        return remote_path

    def _mega_cleanup(self, remote_path: str) -> None:
        try:
            providers.mega_delete_object(
                remote_path,
                is_configured=self.mega_is_configured,
                run=self._mega_run,
            )
        except Exception:
            pass

    def active_backend(self) -> str:
        adapters = {
            "mega": StorageProviderAdapter(
                name="mega",
                is_configured=self.mega_is_configured,
                has_configuration=providers.mega_credentials_present,
                block_auto_if_present=True,
                unavailable_message="MATERIAL_STORAGE_BACKEND=mega，但 MEGA_EMAIL / MEGA_PASSWORD 未設定，或本機找不到官方 MEGAcmd。",
                partial_configuration_message="MEGA 已設定但官方 MEGAcmd 指令不可用或帳密不完整；不會自動改用 Google Drive。",
            ),
            "oci": StorageProviderAdapter(name="oci", is_configured=providers.oci_is_configured),
            "gdrive": StorageProviderAdapter(name="gdrive", is_configured=providers.gdrive_is_configured),
            "r2": StorageProviderAdapter(name="r2", is_configured=providers.r2_is_configured),
        }
        try:
            return select_backend(self.requested_backend, adapters)
        except StorageConfigurationError as exc:
            raise RuntimeError(str(exc)) from exc

    # ------------------------------------------------------------------
    # Conversion helpers used only by the standalone worker
    # ------------------------------------------------------------------
    def _render_slide_pixmap(self, pix, out_folder: Path, page_no: int) -> Path:
        use_webp = self.slide_format_name == "webp" and Image is not None
        if use_webp:
            output = out_folder / f"slide-{page_no:02d}.webp"
            try:
                with Image.open(io.BytesIO(pix.tobytes("png"))) as image:
                    if image.mode not in {"RGB", "RGBA"}:
                        image = image.convert("RGB")
                    image.save(output, format="WEBP", quality=self.webp_quality, method=6)
                return output
            except Exception:
                pass
        output = out_folder / f"slide-{page_no:02d}.png"
        pix.save(str(output))
        return output

    @staticmethod
    def _slide_local_path(slides_dir: Path, page_no: int) -> Path:
        for ext in ("webp", "png", "jpg", "jpeg"):
            candidate = slides_dir / f"slide-{page_no:02d}.{ext}"
            if candidate.exists():
                return candidate
        return slides_dir / f"slide-{page_no:02d}.png"

    def slide_format(self, slides_dir: Path, page_count: int) -> str:
        if int(page_count or 0) <= 0:
            return ""
        path = self._slide_local_path(slides_dir, 1)
        return path.suffix.lower().lstrip(".") if path.exists() else "png"

    def _linearize_pdf_in_place(self, path: Path) -> bool:
        if not self.pdf_linearize:
            return False
        qpdf = shutil.which("qpdf")
        if not qpdf or not path.exists():
            return False
        temp = path.with_name(path.stem + ".linearized.tmp.pdf")
        try:
            completed = subprocess.run(
                [qpdf, "--linearize", str(path), str(temp)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=180,
                check=False,
            )
            if completed.returncode == 0 and temp.exists() and temp.stat().st_size > 0:
                os.replace(temp, path)
                return True
        except Exception:
            pass
        finally:
            temp.unlink(missing_ok=True)
        return False

    def _save_optimized_pdf(self, source_pdf: Path, output_pdf: Path) -> int:
        if pymupdf is None:
            raise RuntimeError("本機 Worker 缺少 PyMuPDF 套件")
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        document = pymupdf.open(str(source_pdf))
        try:
            page_count = int(document.page_count or 0)
            if page_count <= 0:
                raise RuntimeError("教材頁數為 0，請確認檔案內容是否正確。")
            if self.preview_optimize:
                try:
                    document.save(
                        str(output_pdf),
                        garbage=4,
                        clean=True,
                        deflate=True,
                        deflate_images=True,
                        deflate_fonts=True,
                    )
                except TypeError:
                    document.save(str(output_pdf), garbage=4, clean=True, deflate=True)
            else:
                document.save(str(output_pdf), garbage=3, deflate=True)
        finally:
            document.close()
        self._linearize_pdf_in_place(output_pdf)
        return page_count

    def _office_to_pdf(self, source_path: Path, workdir: Path, *, timeout: int) -> Path:
        profile_dir = workdir / f"profile-{uuid.uuid4().hex}"
        pdf_dir = workdir / f"pdf-{uuid.uuid4().hex}"
        profile_dir.mkdir(parents=True, exist_ok=True)
        pdf_dir.mkdir(parents=True, exist_ok=True)
        command = [
            self.soffice,
            "--headless",
            "--norestore",
            f"-env:UserInstallation=file:///{profile_dir.as_posix()}",
            "--convert-to",
            "pdf",
            "--outdir",
            str(pdf_dir),
            str(source_path),
        ]
        completed = subprocess.run(command, capture_output=True, timeout=timeout, check=False)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.decode(errors="ignore")[:500] or "LibreOffice 轉檔失敗")
        pdfs = list(pdf_dir.glob("*.pdf"))
        if not pdfs:
            raise RuntimeError("LibreOffice 未產生 PDF")
        return pdfs[0]

    def build_single_preview_pdf(self, source_path: Path, output_pdf: Path) -> int:
        ext = source_path.suffix.lower()
        if ext == ".pdf":
            return self._save_optimized_pdf(source_path, output_pdf)
        if ext not in OFFICE_EXT:
            return 0
        with _CONVERSION_LOCK, tempfile.TemporaryDirectory(prefix="teacher-worker-preview-") as temp:
            pdf = self._office_to_pdf(source_path, Path(temp), timeout=240)
            return self._save_optimized_pdf(pdf, output_pdf)

    def convert_pdf_to_images(self, pdf_path: Path, out_folder: Path) -> int:
        if pymupdf is None:
            raise RuntimeError("本機 Worker 缺少 PyMuPDF 套件")
        out_folder.mkdir(parents=True, exist_ok=True)
        document = pymupdf.open(str(pdf_path))
        try:
            matrix = pymupdf.Matrix(170 / 72.0, 170 / 72.0)
            page_count = int(document.page_count or 0)
            for index in range(page_count):
                pixmap = document.load_page(index).get_pixmap(matrix=matrix)
                self._render_slide_pixmap(pixmap, out_folder, index + 1)
            return page_count
        finally:
            document.close()

    def convert_office_to_images(self, source_path: Path, out_folder: Path) -> int:
        with _CONVERSION_LOCK, tempfile.TemporaryDirectory(prefix="teacher-worker-office-") as temp:
            pdf = self._office_to_pdf(source_path, Path(temp), timeout=180)
            return self.convert_pdf_to_images(pdf, out_folder)

    # ------------------------------------------------------------------
    # Canonical-provider upload composition
    # ------------------------------------------------------------------
    @staticmethod
    def _content_type(path_or_name: object) -> str:
        return mimetypes.guess_type(str(path_or_name))[0] or "application/octet-stream"

    def upload_source_to_mega(self, material_id: str, source_path: Path) -> str:
        folder = self._mega_remote_join(self._mega_root(), material_id)
        self._mega_free_guard(source_path.stat().st_size)
        return self._mega_upload_file(source_path, folder, f"source{source_path.suffix.lower()}")

    def upload_material_tree_to_mega(
        self,
        material_id: str,
        source_path: Path,
        slides_dir: Path,
        page_count: int,
    ) -> tuple[str, str, dict[str, Any]]:
        total = source_path.stat().st_size + sum(
            path.stat().st_size for path in slides_dir.glob("slide-*.*")
        )
        self._mega_free_guard(total)
        folder = self._mega_remote_join(self._mega_root(), material_id)
        self._mega_ensure_dir(folder)
        slide_files: dict[str, str] = {}
        try:
            source_remote = self._mega_upload_file(
                source_path,
                folder,
                f"source{source_path.suffix.lower()}",
            )
            for index in range(1, int(page_count or 0) + 1):
                slide = self._slide_local_path(slides_dir, index)
                if slide.exists():
                    slide_files[slide.name] = self._mega_upload_file(slide, folder, slide.name)
            meta = {
                "folderId": folder,
                "sourceFileId": source_remote,
                "slideFiles": slide_files,
                "adapter": "megacmd",
                "slideFormat": self.slide_format(slides_dir, page_count),
            }
            return source_remote, folder, meta
        except Exception:
            self._mega_cleanup(folder)
            raise

    def upload_material_preview_to_mega(
        self,
        material_id: str,
        source_path: Path,
        preview_path: Path,
        page_count: int,
    ) -> tuple[str, str, dict[str, Any]]:
        total = source_path.stat().st_size + (preview_path.stat().st_size if preview_path.exists() else 0)
        self._mega_free_guard(total)
        folder = self._mega_remote_join(self._mega_root(), material_id)
        self._mega_ensure_dir(folder)
        source_name = f"source{source_path.suffix.lower()}"
        try:
            source_remote = self._mega_upload_file(source_path, folder, source_name)
            preview_remote = self._mega_upload_file(preview_path, folder, "preview.pdf")
            meta = {
                "folderId": folder,
                "sourceFileId": source_remote,
                "previewFileId": preview_remote,
                "previewFilename": "preview.pdf",
                "previewMode": "single_pdf",
                "previewBytes": preview_path.stat().st_size if preview_path.exists() else 0,
                "pageCount": int(page_count or 0),
                "adapter": "megacmd",
                "slideFormat": "pdf",
                "cloudObjectCount": 2,
                "uploadStrategy": "single_preview",
            }
            return source_remote, folder, meta
        except Exception:
            self._mega_cleanup(folder)
            raise

    @staticmethod
    def _gdrive_create_folder(service, name: str, parent_id: str, app_properties=None) -> str:
        body = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        if app_properties:
            body["appProperties"] = app_properties
        return service.files().create(body=body, fields="id,name").execute()["id"]

    def _gdrive_upload_file(self, service, local_path: Path, name: str, parent_id: str, app_properties=None):
        body = {"name": name, "parents": [parent_id]}
        if app_properties:
            body["appProperties"] = app_properties
        media = providers.gdrive_media_file_upload(
            local_path,
            mimetype=self._content_type(local_path),
            chunk_mb=providers.GDRIVE_CHUNK_MB,
        )
        return service.files().create(
            body=body,
            media_body=media,
            fields="id,name,size,mimeType",
        ).execute()

    def upload_material_tree_to_gdrive(
        self,
        material_id: str,
        source_path: Path,
        slides_dir: Path,
        page_count: int,
        *,
        original_name: str,
    ) -> tuple[str, str, dict[str, Any]]:
        service = providers.gdrive_service()
        material_folder_id = ""
        try:
            material_folder_id = self._gdrive_create_folder(
                service,
                material_id,
                providers.GDRIVE_FOLDER_ID,
                {"smh_kind": "material", "smh_material_id": material_id},
            )
            source = self._gdrive_upload_file(
                service,
                source_path,
                Path(original_name or source_path.name).name,
                material_folder_id,
                {"smh_kind": "source", "smh_material_id": material_id},
            )
            slides_folder_id = ""
            slide_files: dict[str, str] = {}
            if int(page_count or 0) > 0:
                slides_folder_id = self._gdrive_create_folder(
                    service,
                    "slides",
                    material_folder_id,
                    {"smh_kind": "slides", "smh_material_id": material_id},
                )
                for index in range(1, int(page_count or 0) + 1):
                    slide = self._slide_local_path(slides_dir, index)
                    if slide.exists():
                        uploaded = self._gdrive_upload_file(
                            service,
                            slide,
                            slide.name,
                            slides_folder_id,
                            {
                                "smh_kind": "slide",
                                "smh_material_id": material_id,
                                "smh_page": str(index),
                            },
                        )
                        slide_files[slide.name] = uploaded["id"]
            meta = {
                "materialFolderId": material_folder_id,
                "sourceFileId": source["id"],
                "slidesFolderId": slides_folder_id,
                "slideFiles": slide_files,
                "slideFormat": self.slide_format(slides_dir, page_count),
            }
            return source["id"], slides_folder_id, meta
        except Exception:
            if material_folder_id:
                try:
                    service.files().delete(fileId=material_folder_id).execute()
                except Exception:
                    pass
            raise
