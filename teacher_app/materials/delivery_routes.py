"""Canonical HTTP owner for material/image delivery routes.

Provider-specific transport callbacks remain injected from the compatibility
host while storage provider extraction is completed.  URL ownership and access
checks live here so production no longer copies these route functions from the
legacy host.
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote

from flask import abort, g, jsonify, redirect, send_file, send_from_directory

from teacher_app.auth import rbac_legacy_adapter
from teacher_app.config import teaching_usage_notice
from teacher_app.materials import catalog, repository
from teacher_app.storage.web_runtime import WebStorageRuntime, mega_web_status

try:
    import pymupdf
except ImportError:  # pragma: no cover - deployment dependency is optional at import time
    pymupdf = None


LOGGER = logging.getLogger(__name__)


# 單頁預覽圖第一次被要求時才轉檔，連續翻頁會一頁一頁等。
# 轉完目前這頁後，在背景把後面兩頁也轉好（寫進同一個快取），下一頁幾乎立刻出現。
_PAGE_RENDER_LOCK = threading.Lock()
_PAGE_WARM_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="slide-page-warm")
_PAGE_WARM_PENDING: set[str] = set()
_PAGE_WARM_AHEAD = 2


def _page_cache_target(cache_dir: Path, page_no: int, stamp: str) -> Path:
    return cache_dir / f"page-{page_no:04d}-{stamp}.png"


def _render_presentation_page(pdf_path: Path, page_no: int, target: Path) -> bool:
    """Render one PDF page into the shared cache. Returns False when the page does not exist."""
    with _PAGE_RENDER_LOCK:
        if target.exists() and target.stat().st_size > 0:
            return True
        document = pymupdf.open(str(pdf_path))
        try:
            if page_no > int(document.page_count or 0):
                return False
            page = document.load_page(page_no - 1)
            width = max(1.0, float(page.rect.width))
            scale = max(1.5, min(3.0, 1600.0 / width))
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
            tmp = target.parent / f".render-{page_no:04d}.png"
            pixmap.save(str(tmp))
            tmp.replace(target)
        finally:
            document.close()
    for stale in target.parent.glob(f"page-{page_no:04d}-*.png"):
        if stale != target:
            try:
                stale.unlink()
            except OSError:
                pass
    return True


def _warm_following_pages(pdf_path: Path, cache_dir: Path, stamp: str, page_no: int, total: int) -> None:
    for ahead in range(1, _PAGE_WARM_AHEAD + 1):
        nxt = page_no + ahead
        if total and nxt > total:
            return
        target = _page_cache_target(cache_dir, nxt, stamp)
        key = str(target)
        if target.exists() or key in _PAGE_WARM_PENDING:
            continue
        _PAGE_WARM_PENDING.add(key)

        def job(path=pdf_path, number=nxt, out=target, marker=key):
            try:
                _render_presentation_page(path, number, out)
            except Exception as exc:  # warming is best-effort; the request path reports real errors
                LOGGER.debug("slide page warm failed page=%s error_type=%s", number, type(exc).__name__)
            finally:
                _PAGE_WARM_PENDING.discard(marker)

        try:
            _PAGE_WARM_POOL.submit(job)
        except RuntimeError:
            _PAGE_WARM_PENDING.discard(key)
            return


def _login_required():
    if getattr(g, "teacher_user", None):
        return None
    return jsonify({"error": "請先登入後再使用教材。", "loginRequired": True}), 401


def register_material_delivery_routes(owner, *, paths, storage_runtime=None, material_getter=None):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_material_delivery_routes_registered"):
        return app
    runtime = storage_runtime or WebStorageRuntime(paths)
    get_material = material_getter or repository.get_material

    def uploaded_slide_image(folder, filename):
        denied = _login_required()
        if denied:
            return denied
        if Path(folder).name != folder or Path(filename).name != filename:
            abort(404)
        entry = get_material(folder)
        if not entry or not entry.get("active"):
            abort(404)
        backend = str(entry.get("storageBackend") or "local")
        if backend == "mega":
            meta = entry.get("storageMeta") or {}
            file_id = (meta.get("slideFiles") or {}).get(filename, "")
            if not file_id:
                abort(404)
            try:
                return runtime.mega_send_file(file_id, filename, inline=True)
            except Exception as exc:
                return jsonify({"error": f"MEGA 讀取失敗：{exc}"}), 502
        if backend == "gdrive":
            meta = entry.get("storageMeta") or {}
            file_id = (meta.get("slideFiles") or {}).get(filename, "")
            if not file_id:
                file_id = runtime.gdrive_find_file_in_folder(entry.get("slidesPrefix", ""), filename)
            try:
                return runtime.gdrive_proxy_file(file_id, filename, inline=True)
            except Exception as exc:
                return jsonify({"error": f"Google Drive 讀取失敗：{exc}"}), 502
        if backend == "oci":
            prefix = entry.get("slidesPrefix") or f"materials/{entry['id']}/slides"
            try:
                return redirect(runtime.oci_presigned_get(f"{prefix}/{filename}", download_name=filename, inline=True), code=302)
            except Exception as exc:
                return jsonify({"error": f"Oracle Object Storage 讀取失敗：{exc}"}), 502
        if backend == "r2":
            prefix = entry.get("slidesPrefix") or f"materials/{entry['id']}/slides"
            try:
                return redirect(runtime.r2_presigned_get(f"{prefix}/{filename}", download_name=filename, inline=True), code=302)
            except Exception as exc:
                return jsonify({"error": f"R2 讀取失敗：{exc}"}), 502
        return send_from_directory(paths.uploaded_slides_dir / folder, filename)

    def download_slide(slide_id):
        denied = _login_required()
        if denied:
            return denied
        denied = rbac_legacy_adapter.legacy_admin_guard(app)
        if denied:
            return denied
        entry = next((item for item in catalog.load_builtin_meta() if item["id"] == slide_id), None)
        if entry and entry.get("isBuiltin"):
            return send_from_directory(paths.static_dir, entry["filename"], as_attachment=True, download_name=entry["filename"])
        entry = get_material(slide_id)
        if not entry:
            abort(404)
        backend = str(entry.get("storageBackend") or "local")
        if backend == "mega":
            try:
                return runtime.mega_send_file(entry.get("storageKey", ""), entry["filename"], inline=False)
            except Exception as exc:
                return jsonify({"error": f"MEGA 下載失敗：{exc}", "retryable": True}), mega_web_status(exc)
        if backend == "gdrive":
            try:
                return runtime.gdrive_proxy_file(entry.get("storageKey", ""), entry["filename"], inline=False)
            except Exception as exc:
                return jsonify({"error": f"Google Drive 下載失敗：{exc}"}), 502
        if backend == "oci":
            key = entry.get("storageKey") or f"materials/{entry['id']}/{entry.get('storageFilename','source')}"
            try:
                return redirect(runtime.oci_presigned_get(key, download_name=entry["filename"], inline=False), code=302)
            except Exception as exc:
                return jsonify({"error": f"Oracle Object Storage 下載連結產生失敗：{exc}"}), 502
        if backend == "r2":
            key = entry.get("storageKey") or f"materials/{entry['id']}/{entry.get('storageFilename','source')}"
            try:
                return redirect(runtime.r2_presigned_get(key, download_name=entry["filename"], inline=False), code=302)
            except Exception as exc:
                return jsonify({"error": f"R2 下載連結產生失敗：{exc}"}), 502
        path = paths.upload_dir / entry["id"] / entry["storageFilename"]
        if not path.exists():
            abort(404)
        return send_file(path, as_attachment=True, download_name=entry["filename"])

    def material_preview(material_id):
        denied = _login_required()
        if denied:
            return denied
        entry = get_material(material_id)
        if not entry or not entry.get("active"):
            abort(404)
        meta = entry.get("storageMeta") or {}
        if meta.get("previewMode") != "single_pdf":
            abort(404)
        if entry.get("storageBackend") != "mega":
            return jsonify({"error": "此教材的單一預覽目前僅支援 MEGA 儲存模式。"}), 409
        try:
            path = runtime.mega_cached_preview(entry)
            response = send_file(
                path,
                mimetype="application/pdf",
                as_attachment=False,
                download_name="teaching-preview.pdf",
                conditional=True,
                max_age=300,
            )
            response.headers["Content-Disposition"] = 'inline; filename="teaching-preview.pdf"'
            response.headers["Cache-Control"] = "private, max-age=300"
            response.headers["Accept-Ranges"] = "bytes"
            response.headers["X-Preview-Mode"] = "single-pdf-range"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
            response.headers["X-Teaching-Use-Notice"] = quote(teaching_usage_notice(), safe="")
            return response
        except Exception as exc:
            return jsonify({"error": f"教材預覽讀取失敗：{exc}", "retryable": True}), mega_web_status(exc)

    def material_preview_page(material_id, page_no):
        """Render one legacy single-PDF presentation page as an image.

        PowerPoint-like readers use this instead of Chrome's native PDF iframe,
        eliminating the page-1 flash/reload cycle while preserving the existing
        cached preview PDF as the source of truth.
        """
        denied = _login_required()
        if denied:
            return denied
        entry = get_material(material_id)
        if not entry or not entry.get("active"):
            abort(404)
        meta = entry.get("storageMeta") or {}
        if meta.get("previewMode") != "single_pdf":
            abort(404)
        total = max(0, int(entry.get("pageCount", 0) or meta.get("pageCount", 0) or 0))
        page_no = int(page_no or 0)
        if page_no < 1 or (total and page_no > total):
            abort(404)
        if entry.get("storageBackend") != "mega":
            return jsonify({"error": "此教材的單頁預覽目前僅支援 MEGA 儲存模式。"}), 409
        if pymupdf is None:
            return jsonify({"error": "伺服器缺少 PDF 單頁預覽元件。"}), 503
        try:
            pdf_path = Path(runtime.mega_cached_preview(entry))
            stat = pdf_path.stat()
            safe_id = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(material_id))[:120] or "material"
            cache_dir = Path(paths.preview_cache_dir) / "presentation-pages" / safe_id
            cache_dir.mkdir(parents=True, exist_ok=True)
            stamp = f"{stat.st_size}-{stat.st_mtime_ns}"
            target = _page_cache_target(cache_dir, page_no, stamp)
            if not target.exists() or target.stat().st_size <= 0:
                if not _render_presentation_page(pdf_path, page_no, target):
                    abort(404)
            _warm_following_pages(pdf_path, cache_dir, stamp, page_no, total)
            response = send_file(
                target,
                mimetype="image/png",
                as_attachment=False,
                conditional=True,
                max_age=300,
            )
            response.headers["Cache-Control"] = "private, max-age=300"
            response.headers["X-Preview-Mode"] = "presentation-page-image"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
            response.headers["X-Teaching-Use-Notice"] = quote(teaching_usage_notice(), safe="")
            return response
        except Exception as exc:
            if getattr(exc, "code", None) == 404:
                raise
            return jsonify({"error": f"教材單頁預覽讀取失敗：{exc}", "retryable": True}), mega_web_status(exc)

    def view_material(material_id):
        denied = _login_required()
        if denied:
            return denied
        entry = get_material(material_id)
        if not entry or not entry.get("active"):
            abort(404)
        if entry.get("viewerMode") == "slides" or int(entry.get("pageCount", 0) or 0) > 0:
            abort(403)
        backend = str(entry.get("storageBackend") or "local")
        if backend == "mega":
            try:
                return runtime.mega_send_file(entry.get("storageKey", ""), entry["filename"], inline=True)
            except Exception as exc:
                return jsonify({"error": f"MEGA 檢視失敗：{exc}", "retryable": True}), mega_web_status(exc)
        if backend == "gdrive":
            try:
                return runtime.gdrive_proxy_file(entry.get("storageKey", ""), entry["filename"], inline=True)
            except Exception as exc:
                return jsonify({"error": f"Google Drive 檢視失敗：{exc}"}), 502
        if backend == "oci":
            key = entry.get("storageKey") or f"materials/{entry['id']}/{entry.get('storageFilename','source')}"
            try:
                return redirect(runtime.oci_presigned_get(key, download_name=entry["filename"], inline=True), code=302)
            except Exception as exc:
                return jsonify({"error": f"Oracle Object Storage 檢視連結產生失敗：{exc}"}), 502
        if backend == "r2":
            key = entry.get("storageKey") or f"materials/{entry['id']}/{entry.get('storageFilename','source')}"
            try:
                return redirect(runtime.r2_presigned_get(key, download_name=entry["filename"], inline=True), code=302)
            except Exception as exc:
                return jsonify({"error": f"R2 檢視連結產生失敗：{exc}"}), 502
        path = paths.upload_dir / entry["id"] / entry["storageFilename"]
        if not path.exists():
            abort(404)
        return send_file(path, as_attachment=False, download_name=entry["filename"])

    def question_image(name):
        denied = _login_required()
        if denied:
            return denied
        safe = Path(name).name
        local = paths.question_images_dir / safe
        if local.exists():
            return send_from_directory(str(paths.question_images_dir), safe)
        if runtime.active_backend() == "mega" and runtime.mega_is_configured():
            try:
                remote = runtime.mega_remote_join(runtime.mega_root(), "question-images", safe)
                return runtime.mega_send_file(remote, safe, inline=True)
            except Exception as exc:
                LOGGER.warning(
                    "material question image remote read failed backend=mega error_type=%s",
                    type(exc).__name__,
                )
        return jsonify({"error": "找不到題目影像"}), 404

    for rule, endpoint, view in (
        ("/uploaded-slides/<folder>/<path:filename>", "uploaded_slide_image", uploaded_slide_image),
        ("/download/<slide_id>", "download_slide", download_slide),
        ("/material-preview/<material_id>", "material_preview", material_preview),
        ("/material-preview/<material_id>/page/<int:page_no>.png", "material_preview_page", material_preview_page),
        ("/view/<material_id>", "view_material", view_material),
        ("/question-images/<path:name>", "question_image", question_image),
    ):
        app.add_url_rule(rule, endpoint=endpoint, view_func=view, methods=["GET"])

    app.extensions["teacher_material_delivery_routes_registered"] = True
    return app


__all__ = ["register_material_delivery_routes"]
