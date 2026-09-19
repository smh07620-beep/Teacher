"""Canonical synchronous material-upload orchestration.

The synchronous ``/api/slides/upload`` endpoint is retained for compatibility,
while the main admin UI uses the background material-job pipeline. This module
owns the compatibility workflow without Flask request globals or cloud
credentials; conversion/provider operations come from the canonical sync runtime.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from teacher_app.assessments import repository as assessment_repository
from teacher_app.common import scope
from teacher_app.courses import repository as course_repository
from teacher_app.materials import catalog
from teacher_app.materials import repository as material_repository
from teacher_app.materials.validation import ALLOWED_MATERIAL_EXTENSIONS


OFFICE_EXT = frozenset({".pptx", ".ppt", ".doc", ".docx", ".xls", ".xlsx", ".odp", ".odt", ".ods"})
MATERIAL_TYPE_VALUES = frozenset(material_repository.MATERIAL_TYPES)


class SyncUploadError(RuntimeError):
    def __init__(self, message: str, status: int, *, body: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.status = int(status)
        self.body = dict(body or {"error": message})


@dataclass
class SyncUploadRuntime:
    """Injected web-runtime seams; no provider credentials live here."""

    paths_provider: Callable[[], Any]
    active_material_backend: Callable[[], str]
    classify_uploaded_material: Callable[..., tuple[str, str, str]]
    extract_pdf_text: Callable[[Path], str]
    build_single_preview_pdf: Callable[..., int]
    convert_pdf_to_images: Callable[..., int]
    convert_office_to_images: Callable[..., int]
    slide_format: Callable[[Path, int], str]
    upload_material_preview_to_mega: Callable[..., tuple[str, str, dict]]
    upload_material_tree_to_mega: Callable[..., tuple[str, str, dict]]
    upload_material_tree_to_oci: Callable[..., tuple[str, str]]
    upload_material_tree_to_gdrive: Callable[..., tuple[str, str, dict]]
    upload_material_tree_to_r2: Callable[..., tuple[str, str]]
    mega_failover_ready: Callable[[], str]
    is_mega_capacity_full_error: Callable[[Exception], bool]
    mega_destroy: Callable[[str], Any]
    r2_delete_prefix: Callable[[str], Any]
    preview_cache_cleanup: Callable[..., Any]
    set_progress: Callable[..., Any]
    clear_progress: Callable[[str], Any]
    single_preview_enabled: bool = True


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _category_label(category: str) -> str:
    if not category:
        return catalog.CATEGORY_LABELS[""]
    item = assessment_repository.get_category_full(category)
    if item:
        return str(item.get("title") or category)
    return catalog.CATEGORY_LABELS.get(category, catalog.CATEGORY_LABELS[""])


def _progress(runtime: SyncUploadRuntime, progress_id: str, percent: float, stage: str, detail: str = "") -> None:
    if progress_id:
        runtime.set_progress(progress_id, percent, stage, detail)


def process_upload(storage, form: Mapping[str, Any], runtime: SyncUploadRuntime) -> dict:
    """Process one synchronous compatibility upload and return legacy JSON data."""

    progress_id = str(form.get("progressId", "") or "").strip()[:80]
    if progress_id:
        runtime.clear_progress(progress_id)
        _progress(
            runtime,
            progress_id,
            2,
            "接收教材",
            f"正在接收 {Path(getattr(storage, 'filename', '') or '教材').name}",
        )

    group = scope.normalize_group(form.get("group", scope.DEFAULT_GROUP))
    area = scope.normalize_area(form.get("area", scope.DEFAULT_TRAINING_AREA))
    category = str(form.get("category", "") or "")
    course_id = str(form.get("courseId", "") or "").strip()
    course = course_repository.get_course(course_id) if course_id else None
    if not course or course.get("group") != group or course.get("area") != area:
        course_id = ""
    category_row = assessment_repository.get_category_full(category) if category else None
    if category and (
        not category_row
        or category_row.get("group") != group
        or category_row.get("area") != area
    ):
        category = ""

    title = str(form.get("title", "") or "").strip()
    description = str(form.get("desc", "") or "").strip()
    requested_material_type = str(form.get("materialType", "standard") or "standard").strip().lower()
    if requested_material_type not in MATERIAL_TYPE_VALUES | {"auto"}:
        requested_material_type = "standard"
    material_type = requested_material_type
    raw_atlas_meta = {
        "category": str(form.get("atlasCategory", "") or "").strip()[:120],
        "magnification": str(form.get("atlasMagnification", "") or "").strip()[:80],
        "interpretation": str(form.get("atlasInterpretation", "") or "").strip()[:1000],
        "clinical": str(form.get("atlasClinical", "") or "").strip()[:1000],
        "differential": str(form.get("atlasDifferential", "") or "").strip()[:1000],
        "normality": str(form.get("atlasNormality", "") or "").strip()[:40],
        "tags": str(form.get("atlasTags", "") or "").strip()[:300],
    }
    atlas_meta: dict[str, Any] = {}
    classification_method = "人工指定"
    classification_reason = ""

    original_name = Path(str(getattr(storage, "filename", "") or "untitled")).name
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_MATERIAL_EXTENSIONS:
        raise SyncUploadError(
            "不支援此檔案格式。可上傳簡報、PDF、Office 文件、圖片、影音、文字與 ZIP。",
            400,
        )

    try:
        backend = runtime.active_material_backend()
    except Exception as exc:
        raise SyncUploadError(str(exc), 503) from exc

    requested_material_id = str(form.get("materialId", "") or "").strip().lower()
    material_id = (
        requested_material_id
        if re.fullmatch(r"upload-[a-f0-9]{12}", requested_material_id)
        else f"upload-{uuid.uuid4().hex[:12]}"
    )
    existing = material_repository.get_material(material_id)
    if existing:
        return existing

    paths = runtime.paths_provider()
    material_dir = paths.upload_dir / material_id
    out_folder = paths.uploaded_slides_dir / material_id
    material_dir.mkdir(parents=True, exist_ok=True)
    out_folder.mkdir(parents=True, exist_ok=True)
    saved_path = material_dir / f"source{ext}"
    storage.save(str(saved_path))
    _progress(runtime, progress_id, 8, "教材已接收", f"{original_name} 已上傳至伺服器，開始處理")

    storage_meta: dict[str, Any] = {}
    preview_path = material_dir / "preview.pdf"
    try:
        single_preview = bool(
            backend == "mega"
            and runtime.single_preview_enabled
            and (ext == ".pdf" or ext in OFFICE_EXT)
        )
        preview_ready = False
        page_count = 0
        classification_text = None

        if requested_material_type == "auto" and single_preview:
            page_count = runtime.build_single_preview_pdf(
                saved_path,
                preview_path,
                progress_id=progress_id,
            )
            preview_ready = True
            try:
                classification_text = runtime.extract_pdf_text(preview_path)
            except Exception:
                classification_text = None

        if requested_material_type == "auto":
            _progress(
                runtime,
                progress_id,
                47 if preview_ready else 9,
                "智慧分類教材",
                "正在依檔名、教材內容與可用的免費 AI 判斷教材模組",
            )
            material_type, classification_method, classification_reason = runtime.classify_uploaded_material(
                saved_path,
                original_name,
                title,
                description,
                text_override=classification_text,
            )
        else:
            material_type = requested_material_type
        if material_type not in MATERIAL_TYPE_VALUES:
            material_type = "standard"
        atlas_meta = raw_atlas_meta if material_type == "atlas" else {}
        if requested_material_type == "auto":
            _progress(
                runtime,
                progress_id,
                48 if preview_ready else 11,
                "教材分類完成",
                f"{classification_method}：{material_type}{(' · ' + classification_reason) if classification_reason else ''}",
            )

        if single_preview:
            if not preview_ready:
                page_count = runtime.build_single_preview_pdf(
                    saved_path,
                    preview_path,
                    progress_id=progress_id,
                )
            slide_format = "pdf"
        elif ext == ".pdf":
            page_count = runtime.convert_pdf_to_images(saved_path, out_folder, progress_id=progress_id)
            slide_format = runtime.slide_format(out_folder, page_count)
        elif ext in OFFICE_EXT:
            page_count = runtime.convert_office_to_images(saved_path, out_folder, progress_id=progress_id)
            slide_format = runtime.slide_format(out_folder, page_count)
        else:
            page_count = 0
            slide_format = ""
            _progress(runtime, progress_id, 50, "無需轉換", "此教材將直接上傳雲端儲存")

        source_bytes = saved_path.stat().st_size if saved_path.exists() else 0
        supplied_hash = str(form.get("sourceSha256", "") or "").strip().lower()
        source_sha256 = supplied_hash if re.fullmatch(r"[a-f0-9]{64}", supplied_hash) else _sha256_file(saved_path)
        if page_count:
            slide_bytes = (
                preview_path.stat().st_size
                if single_preview and preview_path.exists()
                else sum(path.stat().st_size for path in out_folder.glob("slide-*.*"))
            )
        else:
            slide_bytes = 0
        storage_key = ""
        slides_prefix = ""
        storage_meta = {
            "slideFormat": slide_format,
            "sourceBytes": source_bytes,
            "slideBytes": slide_bytes,
            "sourceSha256": source_sha256,
        }
        if single_preview:
            storage_meta.update(
                {
                    "previewMode": "single_pdf",
                    "previewFilename": "preview.pdf",
                    "previewBytes": slide_bytes,
                }
            )

        original_backend = backend
        try:
            if backend == "mega":
                if single_preview:
                    storage_key, slides_prefix, remote_meta = runtime.upload_material_preview_to_mega(
                        material_id,
                        saved_path,
                        preview_path,
                        page_count,
                        progress_id=progress_id,
                    )
                else:
                    storage_key, slides_prefix, remote_meta = runtime.upload_material_tree_to_mega(
                        material_id,
                        saved_path,
                        out_folder,
                        page_count,
                        progress_id=progress_id,
                    )
                storage_meta.update(remote_meta or {})
            elif backend == "oci":
                storage_key, slides_prefix = runtime.upload_material_tree_to_oci(
                    material_id, saved_path, out_folder, page_count
                )
            elif backend == "gdrive":
                storage_key, slides_prefix, remote_meta = runtime.upload_material_tree_to_gdrive(
                    material_id,
                    saved_path,
                    out_folder,
                    page_count,
                    original_name=original_name,
                )
                storage_meta.update(remote_meta or {})
            elif backend == "r2":
                storage_key, slides_prefix = runtime.upload_material_tree_to_r2(
                    material_id, saved_path, out_folder, page_count
                )
        except Exception as primary_error:
            fallback = (
                runtime.mega_failover_ready()
                if backend == "mega" and runtime.is_mega_capacity_full_error(primary_error)
                else ""
            )
            if not fallback:
                raise
            if single_preview and page_count > 0:
                _progress(
                    runtime,
                    progress_id,
                    50,
                    "啟用雲端備援",
                    f"MEGA 容量不足，正在為 {fallback} 建立相容閱讀頁面",
                )
                shutil.rmtree(out_folder, ignore_errors=True)
                out_folder.mkdir(parents=True, exist_ok=True)
                runtime.convert_pdf_to_images(preview_path, out_folder, progress_id=progress_id)
                slide_format = runtime.slide_format(out_folder, page_count)
                slide_bytes = sum(path.stat().st_size for path in out_folder.glob("slide-*.*"))
                for key in (
                    "previewMode",
                    "previewFilename",
                    "previewBytes",
                    "previewFileId",
                    "pageCount",
                ):
                    storage_meta.pop(key, None)
                storage_meta.update({"slideFormat": slide_format, "slideBytes": slide_bytes})
                single_preview = False
            backend = fallback
            storage_key = ""
            slides_prefix = ""
            storage_meta.update(
                {"failoverFrom": original_backend, "failoverReason": "primary_storage_full"}
            )
            if backend == "gdrive":
                storage_key, slides_prefix, remote_meta = runtime.upload_material_tree_to_gdrive(
                    material_id,
                    saved_path,
                    out_folder,
                    page_count,
                    original_name=original_name,
                )
                storage_meta.update(remote_meta or {})
            elif backend == "r2":
                storage_key, slides_prefix = runtime.upload_material_tree_to_r2(
                    material_id, saved_path, out_folder, page_count
                )
            elif backend == "oci":
                storage_key, slides_prefix = runtime.upload_material_tree_to_oci(
                    material_id, saved_path, out_folder, page_count
                )
            else:
                raise primary_error

        _progress(runtime, progress_id, 94, "寫入教材資料", "雲端檔案已完成，正在同步 Supabase/資料庫")
        date_added = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = {
            "id": material_id,
            "filename": original_name,
            "title": title or original_name,
            "description": description or "管理者上傳之教育訓練補充教材",
            "category": category,
            "group_key": group,
            "training_area": area,
            "course_id": course_id,
            "folder": material_id,
            "page_count": page_count,
            "date_added": date_added,
            "storage_filename": saved_path.name,
            "storage_backend": backend,
            "storage_key": storage_key,
            "slides_prefix": slides_prefix,
            "storage_meta": json.dumps(storage_meta, ensure_ascii=False),
            "material_type": material_type,
            "atlas_meta": json.dumps(atlas_meta, ensure_ascii=False),
            "active": True,
        }
        material_repository.insert_material(entry)

        if backend == "mega" and single_preview and preview_path.exists():
            try:
                cache_target = paths.preview_cache_dir / (
                    re.sub(r"[^A-Za-z0-9_-]", "_", str(material_id)) + ".pdf"
                )
                shutil.copy2(preview_path, cache_target)
                runtime.preview_cache_cleanup(protect=cache_target)
            except Exception:
                pass
        if backend in {"r2", "gdrive", "oci", "mega"}:
            shutil.rmtree(material_dir, ignore_errors=True)
            shutil.rmtree(out_folder, ignore_errors=True)

        _progress(
            runtime,
            progress_id,
            100,
            "教材建立完成",
            "教材、單一預覽檔／閱讀頁與資料庫皆已完成同步",
        )
        return {
            "id": material_id,
            "filename": original_name,
            "title": entry["title"],
            "desc": entry["description"],
            "category": category,
            "group": group,
            "area": area,
            "courseId": course_id,
            "folder": material_id,
            "pageCount": page_count,
            "isBuiltin": False,
            "dateAdded": date_added,
            "active": True,
            "storageBackend": backend,
            "storageMeta": storage_meta,
            "slideFormat": slide_format,
            "materialType": material_type,
            "atlasMeta": atlas_meta,
            "classificationMethod": classification_method,
            "classificationReason": classification_reason,
            "categoryLabel": _category_label(category),
            "imageFolder": f"uploaded-slides/{material_id}",
            "previewUrl": (
                f"/material-preview/{material_id}"
                if (storage_meta or {}).get("previewMode") == "single_pdf"
                else ""
            ),
            "viewerMode": (
                "preview_pdf"
                if (storage_meta or {}).get("previewMode") == "single_pdf"
                else ("slides" if page_count > 0 else "download")
            ),
            "viewUrl": "" if page_count > 0 else f"/view/{material_id}",
        }
    except Exception as exc:
        _progress(runtime, progress_id, 0, "教材建立失敗", str(exc)[:500])
        if backend == "mega":
            try:
                runtime.mega_destroy((storage_meta or {}).get("folderId", ""))
            except Exception:
                pass
        if backend == "r2":
            try:
                runtime.r2_delete_prefix(f"materials/{material_id}/")
            except Exception:
                pass
        shutil.rmtree(material_dir, ignore_errors=True)
        shutil.rmtree(out_folder, ignore_errors=True)
        raise SyncUploadError(
            f"教材處理/儲存失敗：{exc}",
            500,
            body={
                "error": f"教材處理/儲存失敗：{exc}",
                "stage": "教材建立失敗",
                "detail": str(exc)[:500],
                "retryable": True,
            },
        ) from exc


__all__ = [
    "MATERIAL_TYPE_VALUES",
    "OFFICE_EXT",
    "SyncUploadError",
    "SyncUploadRuntime",
    "process_upload",
]
