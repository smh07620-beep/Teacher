"""AI PowerPoint renderer and worker-side generation orchestration."""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any

from teacher_app.materials import ai_presentation_repository as repository
from teacher_app.materials.ai_presentation_storage import PresentationStorage
from teacher_app.materials import media_script_repository
from teacher_app.materials import repository as material_repository

try:
    from pptx import Presentation
    from pptx.util import Inches
except ImportError:  # pragma: no cover
    Presentation = None
    Inches = None

_MAX_SLIDES = 60
_MAX_BULLETS = 8
_SECRET_MARKERS = (
    "token=", "password=", "secret=", "api_key=", "apikey=", "authorization:",
    "bearer ", "database_url=", "r2_secret", "mega_password", "client_secret=",
)
_LOCAL_PATH_PATTERN = re.compile(r"(?:[a-z]:[\\/]|/(?:home|tmp|var|mnt|etc)/|file://)", re.I)


def _clean(value: Any, limit: int) -> str:
    text = str(value or "").replace("\x00", " ").strip()
    text = "\n".join(" ".join(line.split()) for line in text.splitlines())
    return text[:limit]


def _sensitive_provenance_value(value: Any) -> bool:
    if isinstance(value, list):
        return any(_sensitive_provenance_value(item) for item in value)
    text = str(value or "")
    lowered = text.lower()
    return any(marker in lowered for marker in _SECRET_MARKERS) or bool(_LOCAL_PATH_PATTERN.search(text))


def _provenance(payload: dict[str, Any]) -> str:
    clean = {
        "sourceMaterialId": _clean(payload.get("sourceMaterialId"), 120),
        "sourceDraftId": _clean(payload.get("sourceDraftId"), 120),
        "sourceJobId": _clean(payload.get("sourceJobId"), 120),
        "sourceChunkIds": [_clean(v, 160) for v in list(payload.get("sourceChunkIds") or [])[:30] if _clean(v, 160)],
        "provider": _clean(payload.get("provider"), 80),
        "model": _clean(payload.get("model"), 160),
        "templateId": _clean(payload.get("templateId"), 120),
        "teacherApprovedBy": _clean(payload.get("teacherApprovedBy"), 120),
        "teacherApprovedAt": _clean(payload.get("teacherApprovedAt"), 80),
    }
    if any(_sensitive_provenance_value(value) for value in clean.values()):
        raise ValueError("PowerPoint provenance 含有不允許的敏感資訊或本機路徑。")
    return json.dumps(clean, ensure_ascii=False, separators=(",", ":"))


def _slide_header(line: str):
    patterns = (
        r"^\s*(?:#{1,3}\s*)?第\s*(\d{1,2})\s*(?:張|頁)\s*[：:.\-、]?\s*(.*)$",
        r"^\s*(?:#{1,3}\s*)?(\d{1,2})\s*(?:張|頁)\s*[：:.\-、]?\s*(.*)$",
        r"^\s*(?:#{1,3}\s*)?slide\s*(\d{1,2})\s*[：:.\-]?\s*(.*)$",
    )
    for pattern in patterns:
        match = re.match(pattern, line, re.I)
        if match:
            return int(match.group(1)), match.group(2).strip()
    return None


def parse_slide_outline(body: str, *, fallback_title: str = "AI 教學投影片") -> list[dict]:
    slides, current = [], None

    def push():
        nonlocal current
        if not current:
            return
        title = _clean(current.get("title") or f"第 {len(slides)+1} 張", 180)
        bullets = [_clean(item, 500) for item in current.get("bullets", []) if _clean(item, 500)][:_MAX_BULLETS]
        slides.append({"id": f"s{len(slides)+1}", "order": len(slides)+1, "enabled": True,
                       "title": title or f"第 {len(slides)+1} 張", "bullets": bullets, "speakerNotes": ""})
        current = None

    for raw in str(body or "").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        header = _slide_header(raw)
        if header:
            push(); current = {"title": header[1] or f"第 {header[0]} 張", "bullets": []}; continue
        item = re.sub(r"^\s*(?:[-*•▪◦]|\d+[.)、])\s*", "", raw).strip()
        if not item:
            continue
        if current is None:
            current = {"title": fallback_title if not slides else f"第 {len(slides)+1} 張", "bullets": []}
        current["bullets"].append(item)
        if len(current["bullets"]) >= _MAX_BULLETS:
            push()
    push()
    if not slides:
        raise ValueError("AI 投影片草稿沒有可解析的內容。")
    return slides[:_MAX_SLIDES]


def normalize_slides(slides: list[dict]) -> list[dict]:
    normalized = []
    for index, raw in enumerate(list(slides or [])[:_MAX_SLIDES], 1):
        if not isinstance(raw, dict):
            continue
        normalized.append({
            "id": _clean(raw.get("id") or f"s{index}", 80), "order": index,
            "enabled": bool(raw.get("enabled", True)), "title": _clean(raw.get("title"), 180) or f"第 {index} 張",
            "bullets": [_clean(v, 500) for v in list(raw.get("bullets") or [])[:_MAX_BULLETS] if _clean(v, 500)],
            "speakerNotes": _clean(raw.get("speakerNotes"), 4000),
        })
    if not normalized or not any(item["enabled"] for item in normalized):
        raise ValueError("至少要保留一張啟用的投影片。")
    return normalized


def _write_notes(slide, text: str) -> None:
    try:
        slide.notes_slide.notes_text_frame.text = text
    except Exception:
        pass


def _clear_template_slides(prs) -> None:
    """Keep the template theme/layouts but remove authoring/sample slide instances."""
    slide_ids = list(prs.slides._sldIdLst)
    for slide_id in slide_ids:
        rel_id = slide_id.rId
        prs.slides._sldIdLst.remove(slide_id)
        try:
            prs.part.drop_rel(rel_id)
        except KeyError:
            pass


def render_pptx(*, title: str, slides: list[dict], output_path: Path,
                provenance: dict[str, Any], template_path: Path | None = None) -> Path:
    if Presentation is None or Inches is None:
        raise RuntimeError("AI Worker 尚未安裝 python-pptx；請更新 requirements 後重新啟動。")
    prs = Presentation(str(template_path)) if template_path else Presentation()
    if template_path:
        _clear_template_slides(prs)
    core = prs.core_properties
    core.title = _clean(title, 255)
    core.subject = "Teacher AI reviewed teaching presentation"
    core.keywords = "Teacher,AI,medical-laboratory,review-required"
    core.comments = _provenance(provenance)
    for item in normalize_slides(slides):
        if not item["enabled"]:
            continue
        layouts = prs.slide_layouts
        slide = prs.slides.add_slide(layouts[1] if len(layouts) > 1 else layouts[0])
        if slide.shapes.title is not None:
            slide.shapes.title.text = item["title"]
        body = next((p for p in slide.placeholders if p != slide.shapes.title and hasattr(p, "text_frame")), None)
        if body is None:
            body = slide.shapes.add_textbox(Inches(0.8), Inches(1.8), Inches(11.6), Inches(4.8))
        frame = body.text_frame; frame.clear()
        for index, bullet in enumerate(item["bullets"]):
            paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
            paragraph.text = bullet; paragraph.level = 0
        notes = "\n\n".join(filter(None, [_clean(item.get("speakerNotes"), 4000), "PROVENANCE " + core.comments]))
        _write_notes(slide, notes)
    output_path = Path(output_path); output_path.parent.mkdir(parents=True, exist_ok=True); prs.save(str(output_path))
    if not output_path.is_file() or output_path.stat().st_size < 1024:
        raise RuntimeError("python-pptx 未產生有效 PowerPoint 檔案。")
    return output_path


def _template_location(item: dict) -> dict:
    return {"backend": item.get("storageBackend"), "key": item.get("storageKey"), "sha256": item.get("sha256")}


def _source_context(draft: dict, source: dict, *, template_id: str = "") -> dict[str, Any]:
    chunk_ids = []
    for chunk in list(draft.get("sourceChunks") or []):
        value = str((chunk or {}).get("chunkId") or (chunk or {}).get("id") or "") if isinstance(chunk, dict) else str(chunk or "")
        if value.strip():
            chunk_ids.append(value.strip())
    return {
        "sourceMaterialId": str(source.get("id") or ""), "sourceDraftId": str(draft.get("id") or ""),
        "sourceJobId": str(draft.get("sourceJobId") or ""), "sourceChunkIds": chunk_ids,
        "provider": str(draft.get("provider") or ""), "model": str(draft.get("model") or ""),
        "templateId": str(template_id or ""), "teacherApprovedBy": str(draft.get("approvedBy") or ""),
        "teacherApprovedAt": str(draft.get("approvedAt") or ""),
    }


def _validated_template(template_id: str, *, group: str, area: str):
    template = repository.get_template(template_id) if template_id else None
    if template_id and (not template or not template.get("active") or template.get("group") != group or template.get("area") != area):
        raise RuntimeError("PowerPoint 範本不存在、已停用或超出允許範圍。")
    return template


def generate_presentation(*, job: dict, progress_callback=None, storage: PresentationStorage | None = None) -> dict:
    storage = storage or PresentationStorage()
    existing = repository.get_presentation_by_source_job_id(str(job.get("id") or ""))
    if existing:
        return {"presentationId": existing["id"], "replayed": True}
    draft = media_script_repository.get_script(str(job.get("draftId") or ""))
    if not draft or draft.get("draftType") != "slides" or draft.get("status") != "approved":
        raise RuntimeError("只有已由授課教師核准的投影片大綱可產生 PowerPoint。")
    if not str(draft.get("approvedBy") or "") or not str(draft.get("approvedAt") or ""):
        raise RuntimeError("AI 投影片大綱缺少教師核准紀錄。")
    if str(draft.get("group") or "") != str(job.get("group") or "") or str(draft.get("area") or "") != str(job.get("area") or ""):
        raise RuntimeError("PowerPoint 工作範圍與來源草稿不一致。")
    source = material_repository.get_material(str(draft.get("materialId") or ""))
    if not source or source.get("group") != draft.get("group") or source.get("area") != draft.get("area"):
        raise RuntimeError("來源教材不存在或範圍與 AI 草稿不一致。")
    template_id = str(job.get("templateId") or "")
    template = _validated_template(template_id, group=str(draft.get("group") or ""), area=str(draft.get("area") or ""))
    if progress_callback:
        progress_callback(15, "解析投影片大綱", "整理教師已核准的投影片內容")
    supplied = dict(job.get("request") or {}).get("slides")
    slides = normalize_slides(supplied) if isinstance(supplied, list) else parse_slide_outline(str(draft.get("body") or ""), fallback_title=str(draft.get("title") or "AI 教學投影片"))
    with tempfile.TemporaryDirectory(prefix="teacher-ppt-") as temp:
        root = Path(temp); template_path = None
        if template:
            if progress_callback: progress_callback(30, "下載簡報範本", "從共享 provider 下載組別範本")
            template_path = storage.download(_template_location(template), root / "template.pptx")
        output = root / "presentation.pptx"
        if progress_callback: progress_callback(55, "建立 PowerPoint", "寫入投影片、speaker notes 與 provenance")
        render_pptx(title=str(draft.get("title") or source.get("title") or "AI 教學投影片"), slides=slides,
                    output_path=output, provenance=_source_context(draft, source, template_id=template_id), template_path=template_path)
        if progress_callback: progress_callback(80, "保存 PowerPoint", "將產出檔保存至共享 provider")
        artifact = storage.store(output, namespace="artifacts", object_id=str(job.get("id") or ""), filename=f"{str(draft.get('title') or 'AI教學投影片')[:60]}.pptx")
    created = repository.create_presentation(
        material_id=str(source.get("id") or ""), draft_id=str(draft.get("id") or ""), template_id=template_id,
        group_key=str(draft.get("group") or ""), training_area=str(draft.get("area") or ""),
        title=str(draft.get("title") or source.get("title") or "AI 教學投影片")[:255], slides=slides,
        actor_username=str(job.get("actorUsername") or ""), source_job_id=str(job.get("id") or ""),
        provider=str(draft.get("provider") or ""), model=str(draft.get("model") or ""), artifact=artifact)
    if progress_callback: progress_callback(95, "PowerPoint 已保存", "等待授課教師檢查、編修與核准")
    return {"presentationId": str(created.get("id") or ""), "artifactSha256": str(created.get("artifactSha256") or ""),
            "artifactBytes": int(created.get("artifactBytes") or 0), "replayed": False}


def generate_revision(*, job: dict, progress_callback=None, storage: PresentationStorage | None = None) -> dict:
    """Worker-only render path for an already-created immutable draft revision."""
    storage = storage or PresentationStorage(); request_payload = dict(job.get("request") or {})
    presentation_id = str(request_payload.get("presentationId") or "").strip()
    current = repository.get_presentation(presentation_id)
    if not current:
        raise RuntimeError("找不到待重新產生的 PowerPoint revision。")
    if current.get("status") != "draft":
        raise RuntimeError("只有 draft PowerPoint revision 可以重新產生 artifact。")
    if current.get("artifactStorageKey") and current.get("artifactSha256") and int(current.get("artifactBytes") or 0) > 0:
        return {"presentationId": presentation_id, "artifactSha256": current.get("artifactSha256"), "artifactBytes": current.get("artifactBytes"), "replayed": True}
    if current.get("group") != job.get("group") or current.get("area") != job.get("area"):
        raise RuntimeError("PowerPoint revision 工作範圍不一致。")
    draft = media_script_repository.get_script(str(current.get("draftId") or "")) or {}
    source = material_repository.get_material(str(current.get("materialId") or "")) or {}
    if (
        not draft
        or not source
        or draft.get("group") != current.get("group")
        or source.get("group") != current.get("group")
        or draft.get("area") != current.get("area")
        or source.get("area") != current.get("area")
    ):
        raise RuntimeError("PowerPoint revision 來源不存在或授權範圍已改變。")
    template_id = str(current.get("templateId") or "")
    template = _validated_template(template_id, group=str(current.get("group") or ""), area=str(current.get("area") or ""))
    slides = normalize_slides(list(current.get("slides") or []))
    if progress_callback: progress_callback(25, "準備 PowerPoint revision", "由 AI Worker 重新建立教師編修版本")
    with tempfile.TemporaryDirectory(prefix="teacher-ppt-revision-") as temp:
        root = Path(temp); template_path = None
        if template:
            template_path = storage.download(_template_location(template), root / "template.pptx")
        output = root / "presentation.pptx"
        if progress_callback: progress_callback(55, "建立 PowerPoint revision", "寫入教師調整後內容與安全 provenance")
        render_pptx(title=str(current.get("title") or "AI 教學投影片"), slides=slides, output_path=output,
                    provenance=_source_context(draft, source, template_id=template_id), template_path=template_path)
        if progress_callback: progress_callback(80, "保存 PowerPoint revision", "將新 revision artifact 保存至共享 provider")
        artifact = storage.store(output, namespace="artifacts", object_id=presentation_id,
                                 filename=f"{str(current.get('title') or 'AI教學投影片')[:60]}-r{int(current.get('revisionNumber') or 1)}.pptx")
    updated = repository.update_presentation_artifact(presentation_id, artifact=artifact, actor_username=str(job.get("actorUsername") or ""))
    if not updated:
        raise RuntimeError("PowerPoint revision 已不存在。")
    if progress_callback: progress_callback(95, "PowerPoint revision 已保存", "等待授課教師檢查與核准")
    return {"presentationId": presentation_id, "artifactSha256": updated.get("artifactSha256"),
            "artifactBytes": int(updated.get("artifactBytes") or 0), "replayed": False}


__all__ = ["parse_slide_outline", "normalize_slides", "render_pptx", "generate_presentation", "generate_revision"]
