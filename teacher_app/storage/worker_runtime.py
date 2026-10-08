"""Flask-free storage/runtime adapter for the standalone material worker.

Provider credentials and SDK/session construction stay owned by
``teacher_app.storage.providers``.  This module only composes those canonical
providers with the local worker's conversion and upload workflow.
"""
from __future__ import annotations

import io
import hashlib
import logging
import mimetypes
import ntpath
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from teacher_app.storage import providers
from teacher_app.storage.service import StorageConfigurationError, StorageProviderAdapter, select_backend
from teacher_app.worker.libreoffice_warm import WarmLibreOfficeConverter, default_profile_root

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
LOGGER = logging.getLogger(__name__)


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
        # WebP method 6 is the slowest encoder setting; 4 is visually the same
        # at this quality and much faster on the CPU-only local Worker.
        try:
            self.webp_method = max(0, min(6, int(os.environ.get("MATERIAL_WEBP_METHOD", "4"))))
        except ValueError:
            self.webp_method = 4
        try:
            self.slide_dpi = max(100, min(220, int(os.environ.get("MATERIAL_SLIDE_DPI", "170"))))
        except ValueError:
            self.slide_dpi = 170
        self.soffice = os.environ.get("SOFFICE_PATH", "soffice")
        try:
            warm_startup = float(os.environ.get("MATERIAL_LIBREOFFICE_WARM_STARTUP_SECONDS", "5") or 5)
        except ValueError:
            warm_startup = 5.0
        self.libreoffice_warm_enabled = _env_true("MATERIAL_LIBREOFFICE_WARM_ENABLED", True)
        self._libreoffice_warm = WarmLibreOfficeConverter(
            self.soffice,
            enabled=self.libreoffice_warm_enabled,
            startup_timeout=warm_startup,
        )
        self._last_office_mode = ""
        self._last_office_fallback = ""
        self._last_office_seconds = 0.0
        self._last_render_seconds = 0.0

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
        bases = (
            os.environ.get("LOCALAPPDATA", ""),
            os.environ.get("ProgramFiles", ""),
            os.environ.get("ProgramFiles(x86)", ""),
        )
        values: list[str] = []
        seen: set[str] = set()
        # 排程用 SYSTEM 帳號執行時，看不到其他使用者 AppData 下的 MEGAcmd；
        # 可用 MEGACMD_EXTRA_DIRS（以分號分隔的資料夾）明確指定位置。
        for extra in str(os.environ.get("MEGACMD_EXTRA_DIRS", "")).split(";"):
            extra = extra.strip().strip('"')
            if extra:
                normalized = path_module.normcase(path_module.normpath(extra))
                if normalized not in seen:
                    seen.add(normalized)
                    values.append(extra)
        for base in bases:
            if not base:
                continue
            directory = path_module.join(base, "MEGAcmd")
            normalized = path_module.normcase(path_module.normpath(directory))
            if normalized in seen:
                continue
            seen.add(normalized)
            values.append(directory)
        return values

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
        # MEGAcmd 用 %LOCALAPPDATA%\MEGAcmd\MEGAcmdServer.exe 啟動背景伺服器；
        # SYSTEM 帳號的 LOCALAPPDATA 底下沒有它，所以改指向 MEGACMD_EXTRA_DIRS 的上一層。
        if sys.platform.startswith("win"):
            for extra in str(os.environ.get("MEGACMD_EXTRA_DIRS", "")).split(";"):
                extra = extra.strip().strip('"')
                if extra and path_module.basename(path_module.normpath(extra)).lower() == "megacmd":
                    env["LOCALAPPDATA"] = path_module.dirname(path_module.normpath(extra))
                    break
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

    def _mega_upload_file(
        self,
        local_path: Path,
        folder: str,
        remote_name: str,
        *,
        ensure_folder: bool = True,
    ) -> str:
        self._mega_login()
        folder = self._mega_ensure_dir(folder) if ensure_folder else str(folder)
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
        except Exception as exc:
            LOGGER.warning(
                "storage cleanup failed backend=mega action=delete_object error_type=%s",
                type(exc).__name__,
            )

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


    def startup_preflight(self) -> dict[str, object]:
        """Validate final storage before the Worker is allowed to claim jobs."""

        backend = self.active_backend()
        if backend == "local":
            raise RuntimeError(
                "Local Worker 正式教材儲存需設定 MEGA、Google Drive 或 R2。"
            )
        if backend != "mega":
            return {"ready": True, "backend": backend, "detail": "provider configured"}

        self._mega_login()
        root = self._mega_root()
        with tempfile.TemporaryDirectory(prefix="teacher-storage-preflight-") as temp_name:
            probe = Path(temp_name) / "preflight.txt"
            probe.write_text("teacher-material-worker-preflight\n", encoding="utf-8")
            remote_name = f".worker-preflight-{uuid.uuid4().hex[:12]}.txt"
            remote_path = self._mega_upload_file(probe, root, remote_name)
            try:
                self._mega_run(["mega-rm", "-f", remote_path], timeout=60)
            except Exception as exc:
                raise RuntimeError(
                    "MEGA preflight 寫入成功但清理失敗；Worker 暫停領取新教材。"
                ) from exc
        return {
            "ready": True,
            "backend": "mega",
            "detail": "login/write/delete verified",
        }

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
                    image.save(output, format="WEBP", quality=self.webp_quality, method=self.webp_method)
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
        def check_pdf(candidate: Path) -> None:
            try:
                checked = subprocess.run(
                    [qpdf, "--check", str(candidate)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=120,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise RuntimeError("qpdf PDF 結構檢查失敗。") from exc
            # qpdf uses exit 3 for warnings; exit 2 is a structural/error failure.
            if checked.returncode not in {0, 3}:
                detail = (checked.stderr or checked.stdout or b"").decode(errors="ignore")[-400:]
                raise RuntimeError(f"qpdf 拒絕不安全或損壞的 PDF：{detail or 'invalid PDF'}")
        check_pdf(path)
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
                check_pdf(temp)
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

    def libreoffice_status(self) -> dict[str, object]:
        status = dict(self._libreoffice_warm.status())
        status["mode"] = self._last_office_mode
        status["fallback"] = self._last_office_fallback[:240]
        status["lastOfficeSeconds"] = round(float(self._last_office_seconds), 2)
        status["lastRenderSeconds"] = round(float(self._last_render_seconds), 2)
        return status

    def warmup_libreoffice(self) -> dict[str, object]:
        """Best-effort prewarm; failure never blocks material claims.

        Performs a real conversion of a tiny deck (see ``WarmLibreOfficeConverter.warmup``)
        so the profile/font cache and Impress module are loaded before the first
        real material is claimed.
        """
        if not self.libreoffice_warm_enabled:
            return self.libreoffice_status()
        try:
            with _CONVERSION_LOCK:
                self._libreoffice_warm.warmup()
        except Exception as exc:
            self._libreoffice_warm.last_error = type(exc).__name__
        return self.libreoffice_status()

    def _oneshot_profile_dir(self, workdir: Path, *, fresh: bool) -> Path:
        """Persistent profile for the one-shot path, so it is not a cold start every time."""
        if not fresh:
            persistent = default_profile_root() / "oneshot"
            try:
                persistent.mkdir(parents=True, exist_ok=True)
                for name in (".lock", ".~lock"):
                    (persistent / "user" / name).unlink(missing_ok=True)
                return persistent
            except OSError:
                pass
        profile_dir = workdir / f"profile-{uuid.uuid4().hex}"
        profile_dir.mkdir(parents=True, exist_ok=True)
        return profile_dir

    def _office_to_pdf_once(self, source_path: Path, workdir: Path, *, timeout: int) -> Path:
        try:
            return self._office_to_pdf_once_with_profile(
                source_path,
                workdir,
                timeout=timeout,
                profile_dir=self._oneshot_profile_dir(workdir, fresh=False),
            )
        except subprocess.TimeoutExpired:
            raise
        except RuntimeError:
            # A corrupted persistent profile must not break conversion: retry once
            # with a disposable profile, exactly like the legacy behaviour.
            return self._office_to_pdf_once_with_profile(
                source_path,
                workdir,
                timeout=timeout,
                profile_dir=self._oneshot_profile_dir(workdir, fresh=True),
            )

    def _office_to_pdf_once_with_profile(
        self,
        source_path: Path,
        workdir: Path,
        *,
        timeout: int,
        profile_dir: Path,
    ) -> Path:
        pdf_dir = workdir / f"pdf-{uuid.uuid4().hex}"
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

    def _office_to_pdf(self, source_path: Path, workdir: Path, *, timeout: int) -> Path:
        started = time.monotonic()
        try:
            return self._office_to_pdf_inner(source_path, workdir, timeout=timeout)
        finally:
            self._last_office_seconds = time.monotonic() - started

    def _office_to_pdf_inner(self, source_path: Path, workdir: Path, *, timeout: int) -> Path:
        self._last_office_mode = ""
        self._last_office_fallback = ""
        if self.libreoffice_warm_enabled:
            for attempt in range(2):
                pdf_dir = workdir / f"warm-pdf-{uuid.uuid4().hex}"
                try:
                    pdf = self._libreoffice_warm.convert_to_pdf(
                        source_path,
                        pdf_dir,
                        timeout=timeout,
                    )
                    self._last_office_mode = "warm"
                    return pdf
                except Exception as exc:
                    self._last_office_fallback = str(exc)[:240]
                    if attempt == 0:
                        try:
                            self._libreoffice_warm.restart()
                        except Exception:
                            pass
        pdf = self._office_to_pdf_once(source_path, workdir, timeout=timeout)
        self._last_office_mode = "oneshot"
        return pdf

    def prepare_office_pdf(self, source_path: Path, workdir: Path, *, timeout: int = 240) -> Path:
        source_path = Path(source_path)
        if source_path.suffix.lower() not in OFFICE_EXT:
            raise RuntimeError("不是可轉換的 Office 教材。")
        workdir = Path(workdir)
        workdir.mkdir(parents=True, exist_ok=True)
        with _CONVERSION_LOCK:
            return self._office_to_pdf(source_path, workdir, timeout=timeout)

    def build_single_preview_pdf(
        self,
        source_path: Path,
        output_pdf: Path,
        *,
        prepared_pdf: Path | None = None,
    ) -> int:
        ext = source_path.suffix.lower()
        if ext == ".pdf":
            return self._save_optimized_pdf(source_path, output_pdf)
        if ext not in OFFICE_EXT:
            return 0
        if prepared_pdf is None:
            with tempfile.TemporaryDirectory(prefix="teacher-worker-preview-") as temp:
                pdf = self.prepare_office_pdf(source_path, Path(temp), timeout=240)
                return self._save_optimized_pdf(pdf, output_pdf)
        return self._save_optimized_pdf(Path(prepared_pdf), output_pdf)

    def convert_pdf_to_images(
        self,
        pdf_path: Path,
        out_folder: Path,
        *,
        progress_callback=None,
    ) -> int:
        if pymupdf is None:
            raise RuntimeError("本機 Worker 缺少 PyMuPDF 套件")
        out_folder.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        document = pymupdf.open(str(pdf_path))
        try:
            matrix = pymupdf.Matrix(self.slide_dpi / 72.0, self.slide_dpi / 72.0)
            page_count = int(document.page_count or 0)
            for index in range(page_count):
                pixmap = document.load_page(index).get_pixmap(matrix=matrix)
                self._render_slide_pixmap(pixmap, out_folder, index + 1)
                if callable(progress_callback):
                    progress_callback(index + 1, page_count)
            return page_count
        finally:
            document.close()
            self._last_render_seconds = time.monotonic() - started

    def convert_office_to_images(self, source_path: Path, out_folder: Path) -> int:
        with tempfile.TemporaryDirectory(prefix="teacher-worker-office-") as temp:
            pdf = self.prepare_office_pdf(source_path, Path(temp), timeout=180)
            return self.convert_pdf_to_images(pdf, out_folder)

    # ------------------------------------------------------------------
    # Canonical-provider upload composition
    # ------------------------------------------------------------------
    @staticmethod
    def _content_type(path_or_name: object) -> str:
        return mimetypes.guess_type(str(path_or_name))[0] or "application/octet-stream"

    @staticmethod
    def _r2_object_meta(path: Path, key: str) -> dict[str, Any]:
        path = Path(path)
        return {"key": str(key), "bytes": int(path.stat().st_size)}

    def _r2_put_file(
        self,
        local_path: Path,
        key: str,
        *,
        publish_key: str = "",
        source_sha256: str = "",
        object_key: str = "",
        progress_callback=None,
    ) -> dict[str, Any]:
        path = Path(local_path)
        metadata = {
            "smh-publish-key": str(publish_key or "")[:240],
            "smh-source-sha256": str(source_sha256 or "").lower()[:64],
            "smh-object-key": str(object_key or "")[:240],
        }
        metadata = {k: v for k, v in metadata.items() if v}
        kwargs = {
            "ExtraArgs": {
                "ContentType": self._content_type(path),
                "Metadata": metadata,
            }
        }
        if callable(progress_callback):
            kwargs["Callback"] = lambda transferred: progress_callback(max(0, int(transferred or 0)))
        providers.r2_client().upload_file(
            str(path),
            providers.R2_BUCKET_NAME,
            str(key),
            **kwargs,
        )
        return self._r2_object_meta(path, key)

    def upload_source_to_r2(
        self,
        material_id: str,
        source_path: Path,
        *,
        publish_key: str = "",
        source_sha256: str = "",
        progress_callback=None,
    ) -> tuple[str, str, dict[str, Any]]:
        source_path = Path(source_path)
        prefix = f"materials/{material_id}"
        source_key = f"{prefix}/source{source_path.suffix.lower()}"
        total_bytes = max(1, int(source_path.stat().st_size))
        transferred = 0
        progress_lock = threading.Lock()

        def on_delta(delta: int) -> None:
            nonlocal transferred
            with progress_lock:
                transferred = min(total_bytes, transferred + max(0, int(delta or 0)))
                current = transferred
            if callable(progress_callback):
                progress_callback(current, total_bytes, "原始教材")

        obj = self._r2_put_file(
            source_path,
            source_key,
            publish_key=publish_key,
            source_sha256=source_sha256,
            object_key="source",
            progress_callback=on_delta if callable(progress_callback) else None,
        )
        return source_key, "", {
            "r2Objects": [obj],
            "publishKey": publish_key,
            "sourceSha256": str(source_sha256 or "").lower(),
        }

    def upload_material_tree_to_r2(
        self,
        material_id: str,
        source_path: Path,
        slides_dir: Path,
        page_count: int,
        *,
        derivatives: dict[str, Path] | None = None,
        publish_key: str = "",
        source_sha256: str = "",
        progress_callback=None,
    ) -> tuple[str, str, dict[str, Any]]:
        source_path = Path(source_path)
        slides_dir = Path(slides_dir)
        prefix = f"materials/{material_id}"
        source_key = f"{prefix}/source{source_path.suffix.lower()}"
        slides_prefix = f"{prefix}/slides"
        slide_paths: list[tuple[int, Path]] = []
        for index in range(1, int(page_count or 0) + 1):
            slide = self._slide_local_path(slides_dir, index)
            if slide.exists():
                slide_paths.append((index, slide))
        derivative_paths: list[tuple[str, Path]] = []
        for name, raw_path in (derivatives or {}).items():
            path = Path(raw_path)
            if path.is_file() and path.stat().st_size > 0:
                derivative_paths.append((Path(str(name)).name, path))

        total_bytes = max(
            1,
            int(source_path.stat().st_size)
            + sum(int(path.stat().st_size) for _index, path in slide_paths)
            + sum(int(path.stat().st_size) for _name, path in derivative_paths),
        )
        transferred = 0
        progress_lock = threading.Lock()

        def file_delta(label: str):
            def on_delta(delta: int) -> None:
                nonlocal transferred
                with progress_lock:
                    transferred = min(total_bytes, transferred + max(0, int(delta or 0)))
                    current = transferred
                if callable(progress_callback):
                    progress_callback(current, total_bytes, label)
            return on_delta

        objects = [
            self._r2_put_file(
                source_path,
                source_key,
                publish_key=publish_key,
                source_sha256=source_sha256,
                object_key="source",
                progress_callback=file_delta("原始教材") if callable(progress_callback) else None,
            )
        ]
        slide_files: dict[str, str] = {}
        for index, slide in slide_paths:
            key = f"{slides_prefix}/{slide.name}"
            objects.append(
                self._r2_put_file(
                    slide,
                    key,
                    publish_key=publish_key,
                    source_sha256=source_sha256,
                    object_key=f"slide:{index}",
                    progress_callback=file_delta(f"預覽第 {index}/{len(slide_paths)} 頁") if callable(progress_callback) else None,
                )
            )
            slide_files[slide.name] = key
        derived_files: dict[str, str] = {}
        for safe_name, path in derivative_paths:
            key = f"{prefix}/derived/{safe_name}"
            objects.append(
                self._r2_put_file(
                    path,
                    key,
                    publish_key=publish_key,
                    source_sha256=source_sha256,
                    object_key=f"derived:{safe_name}",
                    progress_callback=file_delta(f"衍生檔 {safe_name}") if callable(progress_callback) else None,
                )
            )
            derived_files[safe_name] = key
        return source_key, slides_prefix, {
            "r2Objects": objects,
            "slideFiles": slide_files,
            "derivedFiles": derived_files,
            "slideFormat": self.slide_format(slides_dir, page_count),
            "publishKey": publish_key,
            "sourceSha256": str(source_sha256 or "").lower(),
        }

    def upload_media_bundle_to_r2(
        self,
        material_id: str,
        source_path: Path,
        derivatives: dict[str, Path],
        *,
        publish_key: str = "",
        source_sha256: str = "",
        progress_callback=None,
    ) -> tuple[str, str, dict[str, Any]]:
        return self.upload_material_tree_to_r2(
            material_id,
            source_path,
            Path(source_path).parent / "_empty-slides",
            0,
            derivatives=derivatives,
            publish_key=publish_key,
            source_sha256=source_sha256,
            progress_callback=progress_callback,
        )

    def upload_source_to_mega(self, material_id: str, source_path: Path) -> str:
        folder = self._mega_remote_join(self._mega_root(), material_id)
        self._mega_free_guard(source_path.stat().st_size)
        return self._mega_upload_file(source_path, folder, f"source{source_path.suffix.lower()}")

    def upload_media_bundle_to_mega(
        self,
        material_id: str,
        source_path: Path,
        derivatives: dict[str, Path],
    ) -> tuple[str, str, dict[str, Any]]:
        files = {
            str(name): Path(path)
            for name, path in (derivatives or {}).items()
            if Path(path).is_file() and Path(path).stat().st_size > 0
        }
        total = source_path.stat().st_size + sum(path.stat().st_size for path in files.values())
        self._mega_free_guard(total)
        folder = self._mega_remote_join(self._mega_root(), material_id)
        self._mega_ensure_dir(folder)
        uploaded: dict[str, str] = {}
        try:
            source_remote = self._mega_upload_file(
                source_path,
                folder,
                f"source{source_path.suffix.lower()}",
                ensure_folder=False,
            )
            for name, path in files.items():
                uploaded[name] = self._mega_upload_file(path, folder, name, ensure_folder=False)
            return source_remote, folder, {
                "folderId": folder,
                "sourceFileId": source_remote,
                "derivedFiles": uploaded,
                "adapter": "megacmd",
            }
        except Exception:
            self._mega_cleanup(folder)
            raise

    def upload_material_tree_to_mega(
        self,
        material_id: str,
        source_path: Path,
        slides_dir: Path,
        page_count: int,
        derivatives: dict[str, Path] | None = None,
    ) -> tuple[str, str, dict[str, Any]]:
        derivative_files = {
            str(name): Path(path)
            for name, path in (derivatives or {}).items()
            if Path(path).is_file() and Path(path).stat().st_size > 0
        }
        total = source_path.stat().st_size + sum(
            path.stat().st_size for path in slides_dir.glob("slide-*.*")
        ) + sum(path.stat().st_size for path in derivative_files.values())
        self._mega_free_guard(total)
        folder = self._mega_remote_join(self._mega_root(), material_id)
        self._mega_ensure_dir(folder)
        slide_files: dict[str, str] = {}
        try:
            source_remote = self._mega_upload_file(
                source_path,
                folder,
                f"source{source_path.suffix.lower()}",
                ensure_folder=False,
            )
            for index in range(1, int(page_count or 0) + 1):
                slide = self._slide_local_path(slides_dir, index)
                if slide.exists():
                    slide_files[slide.name] = self._mega_upload_file(slide, folder, slide.name, ensure_folder=False)
            derived_files = {
                name: self._mega_upload_file(path, folder, name, ensure_folder=False)
                for name, path in derivative_files.items()
            }
            meta = {
                "folderId": folder,
                "sourceFileId": source_remote,
                "slideFiles": slide_files,
                "derivedFiles": derived_files,
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
        derivatives: dict[str, Path] | None = None,
    ) -> tuple[str, str, dict[str, Any]]:
        derivative_files = {
            str(name): Path(path)
            for name, path in (derivatives or {}).items()
            if Path(path).is_file() and Path(path).stat().st_size > 0
        }
        total = (
            source_path.stat().st_size
            + (preview_path.stat().st_size if preview_path.exists() else 0)
            + sum(path.stat().st_size for path in derivative_files.values())
        )
        self._mega_free_guard(total)
        folder = self._mega_remote_join(self._mega_root(), material_id)
        self._mega_ensure_dir(folder)
        source_name = f"source{source_path.suffix.lower()}"
        try:
            source_remote = self._mega_upload_file(source_path, folder, source_name, ensure_folder=False)
            preview_remote = self._mega_upload_file(preview_path, folder, "preview.pdf", ensure_folder=False)
            derived_files = {
                name: self._mega_upload_file(path, folder, name, ensure_folder=False)
                for name, path in derivative_files.items()
            }
            meta = {
                "folderId": folder,
                "sourceFileId": source_remote,
                "previewFileId": preview_remote,
                "derivedFiles": derived_files,
                "previewFilename": "preview.pdf",
                "previewMode": "single_pdf",
                "previewBytes": preview_path.stat().st_size if preview_path.exists() else 0,
                "pageCount": int(page_count or 0),
                "adapter": "megacmd",
                "slideFormat": "pdf",
                "cloudObjectCount": 2 + len(derived_files),
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

    @staticmethod
    def _gdrive_query_literal(value: object) -> str:
        return str(value or "").replace("\\", "\\\\").replace("'", "\\'")

    def _gdrive_find_by_properties(
        self,
        service,
        *,
        parent_id: str,
        app_properties: dict[str, str],
        mime_type: str = "",
    ) -> dict[str, Any] | None:
        clauses = [
            "trashed = false",
            f"'{self._gdrive_query_literal(parent_id)}' in parents",
        ]
        if mime_type:
            clauses.append(f"mimeType = '{self._gdrive_query_literal(mime_type)}'")
        for key, value in sorted((app_properties or {}).items()):
            clauses.append(
                "appProperties has { key='"
                + self._gdrive_query_literal(key)
                + "' and value='"
                + self._gdrive_query_literal(value)
                + "' }"
            )
        response = service.files().list(
            q=" and ".join(clauses),
            spaces="drive",
            fields="files(id,name,size,mimeType,appProperties)",
            pageSize=10,
        ).execute()
        matches = [dict(item) for item in (response.get("files") or []) if item.get("id")]
        if not matches:
            return None
        # appProperties are not a uniqueness constraint. In the unlikely event
        # of a historical/racing duplicate, deterministically reuse one object;
        # do not pretend Drive offers an atomic upsert primitive.
        matches.sort(key=lambda item: str(item.get("id") or ""))
        return matches[0]

    def _gdrive_upsert_folder(
        self,
        service,
        name: str,
        parent_id: str,
        app_properties: dict[str, str],
    ) -> tuple[str, bool]:
        existing = self._gdrive_find_by_properties(
            service,
            parent_id=parent_id,
            app_properties=app_properties,
            mime_type="application/vnd.google-apps.folder",
        )
        if existing:
            return str(existing["id"]), True
        return self._gdrive_create_folder(service, name, parent_id, app_properties), False

    def _gdrive_upload_file(self, service, local_path: Path, name: str, parent_id: str, app_properties=None):
        body = {"name": name, "parents": [parent_id]}
        if app_properties:
            body["appProperties"] = app_properties
        media = providers.gdrive_media_file_upload(
            local_path,
            mimetype=self._content_type(local_path),
            chunk_mb=providers.GDRIVE_CHUNK_MB,
        )
        publish_key = str((app_properties or {}).get("smh_publish_key") or "")
        object_key = str((app_properties or {}).get("smh_object_key") or "")
        if publish_key and object_key:
            existing = self._gdrive_find_by_properties(
                service,
                parent_id=parent_id,
                app_properties={
                    "smh_publish_key": publish_key,
                    "smh_object_key": object_key,
                },
            )
            if existing:
                update_body = {"name": name, "appProperties": dict(app_properties or {})}
                return service.files().update(
                    fileId=str(existing["id"]),
                    body=update_body,
                    media_body=media,
                    fields="id,name,size,mimeType,appProperties",
                ).execute()
        return service.files().create(body=body, media_body=media, fields="id,name,size,mimeType,appProperties").execute()

    def upload_material_tree_to_gdrive(
        self,
        material_id: str,
        source_path: Path,
        slides_dir: Path,
        page_count: int,
        *,
        original_name: str,
        derivatives: dict[str, Path] | None = None,
        publish_key: str = "",
        source_sha256: str = "",
    ) -> tuple[str, str, dict[str, Any]]:
        service = providers.gdrive_service()
        material_folder_id = ""
        reused_material_folder = False
        try:
            material_properties = {"smh_kind": "material", "smh_material_id": material_id}
            if publish_key:
                material_properties.update({
                    "smh_publish_key": publish_key,
                    "smh_source_sha256": str(source_sha256 or "").lower(),
                })
                material_folder_id, reused_material_folder = self._gdrive_upsert_folder(
                    service,
                    material_id,
                    providers.GDRIVE_FOLDER_ID,
                    material_properties,
                )
            else:
                material_folder_id = self._gdrive_create_folder(
                    service, material_id, providers.GDRIVE_FOLDER_ID, material_properties
                )
            source_properties = {"smh_kind": "source", "smh_material_id": material_id}
            if publish_key:
                source_properties.update({"smh_publish_key": publish_key, "smh_object_key": "source"})
            source = self._gdrive_upload_file(
                service,
                source_path,
                Path(original_name or source_path.name).name,
                material_folder_id,
                source_properties,
            )
            slides_folder_id = ""
            slide_files: dict[str, str] = {}
            if int(page_count or 0) > 0:
                slide_folder_properties = {"smh_kind": "slides", "smh_material_id": material_id}
                if publish_key:
                    slide_folder_properties.update({"smh_publish_key": publish_key, "smh_object_key": "slides"})
                    slides_folder_id, _reused = self._gdrive_upsert_folder(
                        service, "slides", material_folder_id, slide_folder_properties
                    )
                else:
                    slides_folder_id = self._gdrive_create_folder(
                        service, "slides", material_folder_id, slide_folder_properties
                    )
                for index in range(1, int(page_count or 0) + 1):
                    slide = self._slide_local_path(slides_dir, index)
                    if slide.exists():
                        slide_properties = {
                            "smh_kind": "slide",
                            "smh_material_id": material_id,
                            "smh_page": str(index),
                        }
                        if publish_key:
                            slide_properties.update({"smh_publish_key": publish_key, "smh_object_key": f"slide:{index}"})
                        uploaded = self._gdrive_upload_file(
                            service,
                            slide,
                            slide.name,
                            slides_folder_id,
                            slide_properties,
                        )
                        slide_files[slide.name] = uploaded["id"]
            derived_files: dict[str, str] = {}
            for name, path in (derivatives or {}).items():
                path = Path(path)
                if not path.is_file() or path.stat().st_size <= 0:
                    continue
                derived_properties = {"smh_kind": "derived", "smh_material_id": material_id}
                if publish_key:
                    derived_properties.update({
                        "smh_publish_key": publish_key,
                        "smh_object_key": "derived:" + hashlib.sha256(str(name).encode("utf-8")).hexdigest()[:20],
                    })
                uploaded = self._gdrive_upload_file(
                    service,
                    path,
                    str(name),
                    material_folder_id,
                    derived_properties,
                )
                derived_files[str(name)] = uploaded["id"]
            meta = {
                "materialFolderId": material_folder_id,
                "sourceFileId": source["id"],
                "slidesFolderId": slides_folder_id,
                "slideFiles": slide_files,
                "derivedFiles": derived_files,
                "slideFormat": self.slide_format(slides_dir, page_count),
                "publishKey": publish_key,
            }
            return source["id"], slides_folder_id, meta
        except Exception:
            if material_folder_id and not reused_material_folder:
                try:
                    service.files().delete(fileId=material_folder_id).execute()
                except Exception as cleanup_exc:
                    LOGGER.warning(
                        "storage cleanup failed backend=gdrive action=delete_material_folder material_id=%s error_type=%s",
                        str(material_id or "")[:120],
                        type(cleanup_exc).__name__,
                    )
            raise

    def upload_media_bundle_to_gdrive(
        self,
        material_id: str,
        source_path: Path,
        derivatives: dict[str, Path],
        *,
        original_name: str,
        publish_key: str = "",
        source_sha256: str = "",
    ) -> tuple[str, str, dict[str, Any]]:
        service = providers.gdrive_service()
        material_folder_id = ""
        reused_material_folder = False
        try:
            material_properties = {"smh_kind": "material", "smh_material_id": material_id}
            if publish_key:
                material_properties.update({
                    "smh_publish_key": publish_key,
                    "smh_source_sha256": str(source_sha256 or "").lower(),
                })
                material_folder_id, reused_material_folder = self._gdrive_upsert_folder(
                    service, material_id, providers.GDRIVE_FOLDER_ID, material_properties
                )
            else:
                material_folder_id = self._gdrive_create_folder(
                    service, material_id, providers.GDRIVE_FOLDER_ID, material_properties
                )
            source_properties = {"smh_kind": "source", "smh_material_id": material_id}
            if publish_key:
                source_properties.update({"smh_publish_key": publish_key, "smh_object_key": "source"})
            source = self._gdrive_upload_file(
                service,
                source_path,
                Path(original_name or source_path.name).name,
                material_folder_id,
                source_properties,
            )
            uploaded: dict[str, str] = {}
            for name, path in (derivatives or {}).items():
                path = Path(path)
                if not path.is_file() or path.stat().st_size <= 0:
                    continue
                derived_properties = {"smh_kind": "derived", "smh_material_id": material_id}
                if publish_key:
                    derived_properties.update({
                        "smh_publish_key": publish_key,
                        "smh_object_key": "derived:" + hashlib.sha256(str(name).encode("utf-8")).hexdigest()[:20],
                    })
                item = self._gdrive_upload_file(
                    service,
                    path,
                    str(name),
                    material_folder_id,
                    derived_properties,
                )
                uploaded[str(name)] = item["id"]
            return source["id"], material_folder_id, {
                "materialFolderId": material_folder_id,
                "sourceFileId": source["id"],
                "derivedFiles": uploaded,
                "publishKey": publish_key,
            }
        except Exception:
            if material_folder_id and not reused_material_folder:
                try:
                    service.files().delete(fileId=material_folder_id).execute()
                except Exception as cleanup_exc:
                    LOGGER.warning(
                        "storage cleanup failed backend=gdrive action=delete_material_folder material_id=%s error_type=%s",
                        str(material_id or "")[:120],
                        type(cleanup_exc).__name__,
                    )
            raise
