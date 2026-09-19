"""Canonical runtime composition for synchronous material upload.

This module preserves the historical web upload contract while composing only
canonical provider/client, conversion, progress, and storage owners. R2 usage
accounting stays injectable so isolated tests can retain narrow compatibility
seams without reintroducing a broad application owner.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Callable

from teacher_app.materials import classification
from teacher_app.materials import storage as material_storage
from teacher_app.materials import sync_upload
from teacher_app.materials.upload_progress import UploadProgressStore
from teacher_app.storage import providers
from teacher_app.storage import worker_runtime
from teacher_app.storage.web_runtime import WebStorageRuntime
from teacher_app.storage.worker_runtime import WorkerMaterialStorageAdapter


def is_mega_capacity_full_error(exc) -> bool:
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


def _env_true(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class SyncMaterialRuntimeComposer:
    """Build :class:`SyncUploadRuntime` from canonical conversion/providers."""

    def __init__(
        self,
        paths_provider,
        *,
        classify_uploaded_material: Callable | None = None,
        extract_pdf_text: Callable[[Path], str] | None = None,
        storage_adapter: WorkerMaterialStorageAdapter | None = None,
        r2_record_object: Callable[[str, int], None] | None = None,
        r2_record_deleted: Callable[[str], None] | None = None,
    ):
        self.paths_provider = paths_provider
        self.storage = storage_adapter or WorkerMaterialStorageAdapter()
        self.classify_uploaded_material = (
            classify_uploaded_material or classification.classify_uploaded_material
        )
        self.extract_pdf_text = extract_pdf_text or classification.extract_pdf_text
        self.r2_record_object = r2_record_object
        self.r2_record_deleted = r2_record_deleted

    def _progress_store(self) -> UploadProgressStore:
        return UploadProgressStore(self.paths_provider())

    def set_progress(self, *args, **kwargs):
        return self._progress_store().set(*args, **kwargs)

    def clear_progress(self, progress_id: str):
        return self._progress_store().clear(progress_id)

    def build_single_preview_pdf(self, source_path: Path, output_pdf: Path, progress_id: str = "") -> int:
        source_path = Path(source_path)
        output_pdf = Path(output_pdf)
        ext = source_path.suffix.lower()
        if ext == ".pdf":
            if progress_id:
                self.set_progress(
                    progress_id,
                    16,
                    "建立單一預覽檔",
                    "正在整理 PDF 結構與壓縮可安全壓縮的資料…",
                )
            pages = self.storage._save_optimized_pdf(source_path, output_pdf)
            if progress_id:
                self.set_progress(
                    progress_id,
                    46,
                    "單一預覽檔完成",
                    f"已建立 {pages} 頁 preview.pdf，不再產生逐頁圖片",
                    current=pages,
                    total=pages,
                )
            return pages
        if ext not in worker_runtime.OFFICE_EXT:
            return 0
        with worker_runtime._CONVERSION_LOCK, tempfile.TemporaryDirectory(
            prefix="teacher-web-preview-"
        ) as temp:
            workdir = Path(temp)
            if progress_id:
                self.set_progress(
                    progress_id,
                    12,
                    "建立單一預覽檔",
                    "LibreOffice 正在將教材轉為單一 PDF 預覽檔…",
                )
            pdf = self.storage._office_to_pdf(source_path, workdir, timeout=240)
            if progress_id:
                self.set_progress(
                    progress_id,
                    30,
                    "壓縮單一預覽檔",
                    "正在移除 PDF 冗餘物件並壓縮字型／影像資料；不降低醫療圖像解析度",
                )
            pages = self.storage._save_optimized_pdf(pdf, output_pdf)
            if progress_id:
                self.set_progress(
                    progress_id,
                    46,
                    "單一預覽檔完成",
                    f"已建立 {pages} 頁 preview.pdf，不再產生逐頁圖片",
                    current=pages,
                    total=pages,
                )
            return pages

    def convert_pdf_to_images(self, pdf_path: Path, out_folder: Path, progress_id: str = "") -> int:
        if worker_runtime.pymupdf is None:
            raise RuntimeError("伺服器缺少 PyMuPDF 套件")
        out_folder = Path(out_folder)
        out_folder.mkdir(parents=True, exist_ok=True)
        document = worker_runtime.pymupdf.open(str(pdf_path))
        try:
            matrix = worker_runtime.pymupdf.Matrix(170 / 72.0, 170 / 72.0)
            page_count = int(document.page_count or 0)
            if progress_id:
                self.set_progress(
                    progress_id,
                    18,
                    "解析文件頁面",
                    f"偵測到 {page_count} 頁，準備產生高解析投影片圖片",
                    current=0,
                    total=page_count,
                )
            for index in range(page_count):
                pixmap = document.load_page(index).get_pixmap(matrix=matrix)
                self.storage._render_slide_pixmap(pixmap, out_folder, index + 1)
                if progress_id:
                    percent = 18 + ((index + 1) / max(1, page_count)) * 32
                    self.set_progress(
                        progress_id,
                        percent,
                        "產生投影片圖片",
                        f"正在產生第 {index + 1} / {page_count} 張高解析圖片",
                        current=index + 1,
                        total=page_count,
                    )
            return page_count
        finally:
            document.close()

    def convert_office_to_images(self, source_path: Path, out_folder: Path, progress_id: str = "") -> int:
        with worker_runtime._CONVERSION_LOCK, tempfile.TemporaryDirectory(
            prefix="teacher-web-office-"
        ) as temp:
            if progress_id:
                self.set_progress(
                    progress_id,
                    12,
                    "轉換 Office 文件",
                    "LibreOffice 正在轉換為 PDF…",
                )
            pdf = self.storage._office_to_pdf(Path(source_path), Path(temp), timeout=180)
            if progress_id:
                self.set_progress(
                    progress_id,
                    17,
                    "Office 轉檔完成",
                    "開始將 PDF 轉成高解析教材頁面",
                )
            return self.convert_pdf_to_images(pdf, Path(out_folder), progress_id=progress_id)

    def upload_material_tree_to_mega(
        self,
        material_id: str,
        source_path: Path,
        slides_dir: Path,
        page_count: int,
        progress_id: str = "",
    ):
        source_path = Path(source_path)
        slides_dir = Path(slides_dir)
        total = source_path.stat().st_size + sum(
            path.stat().st_size for path in slides_dir.glob("slide-*.*")
        )
        self.storage._mega_free_guard(total)
        folder = self.storage._mega_remote_join(self.storage._mega_root(), material_id)
        self.storage._mega_ensure_dir(folder)
        slide_files = {}
        total_items = 1 + int(page_count or 0)
        try:
            if progress_id:
                self.set_progress(
                    progress_id,
                    54,
                    "上傳雲端教材",
                    "正在上傳原始教材到 MEGA",
                    current=0,
                    total=total_items,
                )
            source_remote = self.storage._mega_upload_file(
                source_path,
                folder,
                f"source{source_path.suffix.lower()}",
            )
            if progress_id:
                self.set_progress(
                    progress_id,
                    60,
                    "原始教材已上傳",
                    f"開始上傳教材頁面，共 {int(page_count or 0)} 張",
                    current=1,
                    total=total_items,
                )
            for index in range(1, int(page_count or 0) + 1):
                slide = self.storage._slide_local_path(slides_dir, index)
                if slide.exists():
                    slide_files[slide.name] = self.storage._mega_upload_file(
                        slide, folder, slide.name
                    )
                if progress_id:
                    percent = 60 + (index / max(1, int(page_count or 0))) * 30
                    self.set_progress(
                        progress_id,
                        percent,
                        "上傳教材頁面",
                        f"MEGA：第 {index} / {int(page_count or 0)} 張",
                        current=index + 1,
                        total=total_items,
                    )
            return source_remote, folder, {
                "folderId": folder,
                "sourceFileId": source_remote,
                "slideFiles": slide_files,
                "adapter": "megacmd",
                "slideFormat": self.storage.slide_format(slides_dir, page_count),
            }
        except Exception:
            self.storage._mega_cleanup(folder)
            raise

    def upload_material_preview_to_mega(
        self,
        material_id: str,
        source_path: Path,
        preview_path: Path,
        page_count: int,
        progress_id: str = "",
    ):
        source_path = Path(source_path)
        preview_path = Path(preview_path)
        total = source_path.stat().st_size + (
            preview_path.stat().st_size if preview_path.exists() else 0
        )
        self.storage._mega_free_guard(total)
        folder = self.storage._mega_remote_join(self.storage._mega_root(), material_id)
        self.storage._mega_ensure_dir(folder)
        source_name = f"source{source_path.suffix.lower()}"
        preview_name = "preview.pdf"
        try:
            if progress_id:
                self.set_progress(
                    progress_id,
                    54,
                    "上傳雲端教材",
                    "MEGA：一次傳送原始檔與單一預覽檔，避免逐頁上傳",
                    current=0,
                    total=2,
                )
            for remote_name in (source_name, preview_name):
                self.storage._mega_run(
                    [
                        "mega-rm",
                        "-f",
                        self.storage._mega_remote_join(folder, remote_name),
                    ],
                    check=False,
                    timeout=60,
                )
            self.storage._mega_run(
                ["mega-put", "-c", str(source_path), str(preview_path), folder],
                timeout=max(providers.MEGACMD_TIMEOUT_SECONDS, 900),
            )
            source_remote = self.storage._mega_remote_join(folder, source_path.name)
            preview_remote = self.storage._mega_remote_join(folder, preview_path.name)
            if source_path.name != source_name:
                self.storage._mega_run(
                    [
                        "mega-mv",
                        source_remote,
                        self.storage._mega_remote_join(folder, source_name),
                    ],
                    timeout=60,
                )
                source_remote = self.storage._mega_remote_join(folder, source_name)
            if preview_path.name != preview_name:
                self.storage._mega_run(
                    [
                        "mega-mv",
                        preview_remote,
                        self.storage._mega_remote_join(folder, preview_name),
                    ],
                    timeout=60,
                )
                preview_remote = self.storage._mega_remote_join(folder, preview_name)
            if progress_id:
                self.set_progress(
                    progress_id,
                    90,
                    "MEGA 上傳完成",
                    "原始教材 + preview.pdf 已完成；不需要逐頁上傳圖片",
                    current=2,
                    total=2,
                )
            return source_remote, folder, {
                "folderId": folder,
                "sourceFileId": source_remote,
                "previewFileId": preview_remote,
                "previewFilename": preview_name,
                "previewMode": "single_pdf",
                "previewBytes": preview_path.stat().st_size if preview_path.exists() else 0,
                "pageCount": int(page_count or 0),
                "adapter": "megacmd",
                "slideFormat": "pdf",
                "cloudObjectCount": 2,
                "uploadStrategy": "single_preview",
            }
        except Exception:
            self.storage._mega_cleanup(folder)
            raise

    def _oci_free_guard(self, extra_bytes: int) -> None:
        if not self.storage.free_only:
            return
        used = material_storage.bucket_usage_bytes(
            providers.oci_client(), providers.OCI_BUCKET_NAME
        )
        limit = int(providers.OCI_FREE_LIMIT_GB * 1024**3)
        if used + int(extra_bytes or 0) > limit:
            raise RuntimeError(
                f"免費模式已鎖定：Oracle 教材空間約 {used/1024**3:.2f}GB，"
                f"新增此檔會超過網站設定的 {providers.OCI_FREE_LIMIT_GB:.1f}GB 上限。請先刪除舊教材。"
            )

    def upload_material_tree_to_oci(self, material_id, source_path, slides_dir, page_count):
        source_path = Path(source_path)
        slides_dir = Path(slides_dir)
        slides = [
            self.storage._slide_local_path(slides_dir, index)
            for index in range(1, int(page_count or 0) + 1)
        ]
        self._oci_free_guard(
            source_path.stat().st_size
            + sum(path.stat().st_size for path in slides if path.exists())
        )
        client = providers.oci_client()
        source_key = f"materials/{material_id}/source{source_path.suffix.lower()}"
        slides_prefix = f"materials/{material_id}/slides"
        client.upload_file(
            str(source_path),
            providers.OCI_BUCKET_NAME,
            source_key,
            ExtraArgs={"ContentType": self.storage._content_type(source_path)},
        )
        for slide in slides:
            if slide.exists():
                client.upload_file(
                    str(slide),
                    providers.OCI_BUCKET_NAME,
                    f"{slides_prefix}/{slide.name}",
                    ExtraArgs={"ContentType": self.storage._content_type(slide)},
                )
        return source_key, slides_prefix

    def _r2_put_file(self, path: Path, key: str) -> None:
        if self.r2_record_object is None:
            raise RuntimeError("R2 使用量 ledger callback 尚未注入。")
        path = Path(path)
        providers.r2_client().upload_file(
            str(path),
            providers.R2_BUCKET_NAME,
            key,
            ExtraArgs={"ContentType": self.storage._content_type(path)},
        )
        self.r2_record_object(key, path.stat().st_size)

    def upload_material_tree_to_r2(self, material_id, source_path, slides_dir, page_count):
        source_path = Path(source_path)
        slides_dir = Path(slides_dir)
        source_key = f"materials/{material_id}/source{source_path.suffix.lower()}"
        slides_prefix = f"materials/{material_id}/slides"
        self._r2_put_file(source_path, source_key)
        for index in range(1, int(page_count or 0) + 1):
            slide = self.storage._slide_local_path(slides_dir, index)
            if slide.exists():
                self._r2_put_file(slide, f"{slides_prefix}/{slide.name}")
        return source_key, slides_prefix

    def r2_delete_prefix(self, prefix: str) -> None:
        if self.r2_record_deleted is None:
            raise RuntimeError("R2 使用量 ledger delete callback 尚未注入。")
        material_storage.delete_prefix(
            providers.r2_client(),
            providers.R2_BUCKET_NAME,
            str(prefix),
            on_deleted=self.r2_record_deleted,
        )

    def mega_failover_ready(self) -> str:
        if not _env_true("STORAGE_FAILOVER_ON_FULL", False):
            return ""
        if os.environ.get("STORAGE_FALLBACK_BACKEND", "").strip().lower() != "gdrive":
            return ""
        return "gdrive" if providers.gdrive_is_configured() else ""

    def preview_cache_cleanup(self, *, protect=None):
        return WebStorageRuntime(
            self.paths_provider(), storage_adapter=self.storage
        )._preview_cache_cleanup(protect=protect)

    def build(self) -> sync_upload.SyncUploadRuntime:
        return sync_upload.SyncUploadRuntime(
            paths_provider=self.paths_provider,
            active_material_backend=self.storage.active_backend,
            classify_uploaded_material=self.classify_uploaded_material,
            extract_pdf_text=self.extract_pdf_text,
            build_single_preview_pdf=self.build_single_preview_pdf,
            convert_pdf_to_images=self.convert_pdf_to_images,
            convert_office_to_images=self.convert_office_to_images,
            slide_format=self.storage.slide_format,
            upload_material_preview_to_mega=self.upload_material_preview_to_mega,
            upload_material_tree_to_mega=self.upload_material_tree_to_mega,
            upload_material_tree_to_oci=self.upload_material_tree_to_oci,
            upload_material_tree_to_gdrive=self.storage.upload_material_tree_to_gdrive,
            upload_material_tree_to_r2=self.upload_material_tree_to_r2,
            mega_failover_ready=self.mega_failover_ready,
            is_mega_capacity_full_error=is_mega_capacity_full_error,
            mega_destroy=self.storage._mega_cleanup,
            r2_delete_prefix=self.r2_delete_prefix,
            preview_cache_cleanup=self.preview_cache_cleanup,
            set_progress=self.set_progress,
            clear_progress=self.clear_progress,
            single_preview_enabled=bool(self.storage.single_preview),
        )


def build_canonical_sync_runtime(
    *,
    paths_provider,
    classify_uploaded_material=None,
    extract_pdf_text=None,
    r2_record_object=None,
    r2_record_deleted=None,
    storage_adapter=None,
) -> sync_upload.SyncUploadRuntime:
    return SyncMaterialRuntimeComposer(
        paths_provider,
        classify_uploaded_material=classify_uploaded_material,
        extract_pdf_text=extract_pdf_text,
        r2_record_object=r2_record_object,
        r2_record_deleted=r2_record_deleted,
        storage_adapter=storage_adapter,
    ).build()


__all__ = [
    "SyncMaterialRuntimeComposer",
    "build_canonical_sync_runtime",
    "is_mega_capacity_full_error",
]
