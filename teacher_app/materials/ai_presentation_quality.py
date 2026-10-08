"""Deterministic Phase 4 quality automation for AI PowerPoint authoring.

This module intentionally contains no Flask or provider code.  It only transforms
already-sanitized slide structures and emits an allow-listed quality manifest so
Web and the AI Worker can make the same decision without trusting model output.
"""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any, Mapping

RULESET_VERSION = "phase4-v1"
_LAYOUT_KINDS = {"title", "section", "content", "image", "comparison", "table", "summary"}
_PLACEHOLDER_ROLES = {"title", "body", "image", "table", "footer"}
_PLACEHOLDER_SELECTORS = {"auto", "title", "body", "picture", "table", "footer"}
_QUALITY_CODES = {
    "TEXT_SPLIT", "TABLE_SPLIT", "COMPARISON_SPLIT", "MISSING_IMAGE",
    "TEMPLATE_FALLBACK", "PROVENANCE_MISSING", "NOTES_MISSING",
    "EMPTY_SLIDE", "NO_RENDERABLE_SLIDES", "OVERFLOW_RISK", "MANUAL_ARTIFACT_UNCHECKED",
    "AUTO_PICTURES",
}
_MAX_QUALITY_ITEMS = 100


def _clean(value: Any, limit: int) -> str:
    text = str(value or "").replace("\x00", " ").strip()
    return "\n".join(" ".join(line.split()) for line in text.splitlines())[:limit]


def _issue(code: str, *, slide_id: str = "", detail: str = "", blocking: bool = False) -> dict[str, Any]:
    safe_code = code if code in _QUALITY_CODES else "OVERFLOW_RISK"
    return {
        "code": safe_code,
        "slideId": _clean(slide_id, 80),
        "detail": _clean(detail, 240),
        "blocking": bool(blocking),
    }


def sanitize_quality_manifest(value: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(value or {})
    warnings = []
    errors = []
    for target, raw_items, blocking in (
        (warnings, payload.get("warnings"), False),
        (errors, payload.get("errors"), True),
    ):
        for raw in list(raw_items or [])[:_MAX_QUALITY_ITEMS]:
            if not isinstance(raw, Mapping):
                continue
            code = str(raw.get("code") or "").strip().upper()
            if code not in _QUALITY_CODES:
                continue
            target.append(_issue(code, slide_id=raw.get("slideId"), detail=raw.get("detail"), blocking=blocking))
    try:
        slide_count = max(0, min(500, int(payload.get("slideCount") or 0)))
    except (TypeError, ValueError):
        slide_count = 0
    status = "error" if errors else ("warning" if warnings else "pass")
    return {
        "version": 1,
        "rulesetVersion": _clean(payload.get("rulesetVersion") or RULESET_VERSION, 40) or RULESET_VERSION,
        "status": status,
        "slideCount": slide_count,
        "warningCount": len(warnings),
        "errorCount": len(errors),
        "warnings": warnings,
        "errors": errors,
    }


def sanitize_render_metrics(value: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(value or {})
    try:
        duration_ms = max(0, min(24 * 60 * 60 * 1000, int(payload.get("durationMs") or 0)))
    except (TypeError, ValueError):
        duration_ms = 0
    try:
        attempts = max(0, min(20, int(payload.get("attempts") or 0)))
    except (TypeError, ValueError):
        attempts = 0
    def bounded_int(name: str, upper: int) -> int:
        try:
            return max(0, min(upper, int(payload.get(name) or 0)))
        except (TypeError, ValueError):
            return 0
    return {
        "rulesetVersion": _clean(payload.get("rulesetVersion") or RULESET_VERSION, 40) or RULESET_VERSION,
        "durationMs": duration_ms,
        "attempts": attempts,
        "jobId": _clean(payload.get("jobId"), 120),
        "lastError": _clean(payload.get("lastError"), 500),
        "templateFallbackCount": bounded_int("templateFallbackCount", 500),
        "renderedSlideCount": bounded_int("renderedSlideCount", 500),
    }


def sanitize_placeholder_map(value: Mapping[str, Any] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for role, selector in dict(value or {}).items():
        key = str(role or "").strip().lower()
        selected = str(selector or "").strip().lower()
        if key in _PLACEHOLDER_ROLES and selected in _PLACEHOLDER_SELECTORS:
            result[key] = selected
    return result


def select_layout(slide: Mapping[str, Any]) -> str:
    """Choose only a known layout from content semantics; model strings are not trusted."""
    blocks = [block for block in list(slide.get("blocks") or []) if isinstance(block, Mapping)]
    kinds = {str(block.get("type") or "").lower() for block in blocks}
    bullets = [str(item or "") for item in list(slide.get("bullets") or []) if str(item or "").strip()]
    requested = str(slide.get("layout") or "content").strip().lower()
    if "table" in kinds:
        return "table"
    if "comparison" in kinds:
        return "comparison"
    # A picture slide with bullets keeps the normal text layout; the renderer puts
    # the picture beside the text. The dedicated picture layout is for picture-only slides.
    if "image" in kinds and not bullets:
        return "image"
    if not bullets and not blocks:
        return requested if requested in {"title", "section", "summary"} else "section"
    if requested in _LAYOUT_KINDS and requested not in {"title", "section"}:
        return requested
    return "content"


def _split_long_text(text: str, *, max_chars: int = 280) -> list[str]:
    value = _clean(text, 2000)
    if len(value) <= max_chars:
        return [value] if value else []
    parts = [part.strip() for part in re.split(r"(?<=[。！？；.!?;])\s*", value) if part.strip()]
    if len(parts) <= 1:
        parts = [value[index:index + max_chars] for index in range(0, len(value), max_chars)]
    output: list[str] = []
    current = ""
    for part in parts:
        candidate = part if not current else f"{current} {part}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                output.append(current)
            current = part
    if current:
        output.append(current)
    return output


def _paginate_bullets(slide: dict[str, Any], warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expanded: list[str] = []
    for bullet in list(slide.get("bullets") or []):
        expanded.extend(_split_long_text(str(bullet or "")))
    if not expanded:
        return [slide]
    pages: list[list[str]] = []
    current: list[str] = []
    chars = 0
    for bullet in expanded:
        cost = len(bullet) + 16
        if current and (len(current) >= 6 or chars + cost > 760):
            pages.append(current)
            current, chars = [], 0
        current.append(bullet)
        chars += cost
    if current:
        pages.append(current)
    if len(pages) <= 1:
        slide["bullets"] = pages[0] if pages else []
        return [slide]
    warnings.append(_issue("TEXT_SPLIT", slide_id=slide.get("id"), detail=f"文字過多，已安全拆成 {len(pages)} 張。"))
    result: list[dict[str, Any]] = []
    for index, bullets in enumerate(pages, 1):
        copy = deepcopy(slide)
        copy["bullets"] = bullets
        if index > 1:
            copy["id"] = f"{slide.get('id')}-text-{index}"
            copy["title"] = f"{slide.get('title')}（續 {index}）"
            copy["blocks"] = []
        result.append(copy)
    return result


def _paginate_table(slide: dict[str, Any], warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks = list(slide.get("blocks") or [])
    table_index = next((idx for idx, block in enumerate(blocks) if block.get("type") == "table"), None)
    if table_index is None:
        return [slide]
    table = blocks[table_index]
    rows = list(table.get("rows") or [])
    if len(rows) <= 7:
        return [slide]
    chunks = [rows[index:index + 7] for index in range(0, len(rows), 7)]
    warnings.append(_issue("TABLE_SPLIT", slide_id=slide.get("id"), detail=f"表格過長，已保留表頭並拆成 {len(chunks)} 張。"))
    output: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks, 1):
        copy = deepcopy(slide)
        copy["id"] = str(slide.get("id") or "") if index == 1 else f"{slide.get('id')}-table-{index}"
        copy["title"] = str(slide.get("title") or "") if index == 1 else f"{slide.get('title')}（續 {index}）"
        copy_blocks = deepcopy(blocks)
        copy_blocks[table_index]["rows"] = chunk
        copy["blocks"] = copy_blocks
        output.append(copy)
    return output


def _paginate_comparison(slide: dict[str, Any], warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks = list(slide.get("blocks") or [])
    index = next((idx for idx, block in enumerate(blocks) if block.get("type") == "comparison"), None)
    if index is None:
        return [slide]
    block = blocks[index]
    left = list(block.get("leftItems") or [])
    right = list(block.get("rightItems") or [])
    pages = max((len(left) + 4) // 5, (len(right) + 4) // 5, 1)
    if pages <= 1:
        return [slide]
    warnings.append(_issue("COMPARISON_SPLIT", slide_id=slide.get("id"), detail=f"比較內容過長，已拆成 {pages} 張。"))
    output: list[dict[str, Any]] = []
    for page in range(pages):
        copy = deepcopy(slide)
        copy["id"] = str(slide.get("id") or "") if page == 0 else f"{slide.get('id')}-comparison-{page + 1}"
        copy["title"] = str(slide.get("title") or "") if page == 0 else f"{slide.get('title')}（續 {page + 1}）"
        copy_blocks = deepcopy(blocks)
        copy_blocks[index]["leftItems"] = left[page * 5:(page + 1) * 5]
        copy_blocks[index]["rightItems"] = right[page * 5:(page + 1) * 5]
        copy["blocks"] = copy_blocks
        output.append(copy)
    return output


def prepare_slides(slides: list[dict[str, Any]], *, provenance_present: bool = True,
                   notes_required: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    prepared: list[dict[str, Any]] = []
    for raw in list(slides or []):
        if not isinstance(raw, Mapping) or not bool(raw.get("enabled", True)):
            continue
        slide = deepcopy(dict(raw))
        slide["layout"] = select_layout(slide)
        slide_id = str(slide.get("id") or "")
        if not str(slide.get("title") or "").strip() and not slide.get("bullets") and not slide.get("blocks"):
            errors.append(_issue("EMPTY_SLIDE", slide_id=slide_id, detail="投影片沒有可顯示內容。", blocking=True))
        if notes_required and not str(slide.get("speakerNotes") or "").strip():
            warnings.append(_issue("NOTES_MISSING", slide_id=slide_id, detail="此張沒有教師 speaker notes。"))
        for block in list(slide.get("blocks") or []):
            if block.get("type") == "image" and not isinstance(block.get("asset"), Mapping):
                warnings.append(_issue("MISSING_IMAGE", slide_id=slide_id, detail="圖片素材不存在，將使用安全替代區塊。"))
        pages = [slide]
        pages = [item for page in pages for item in _paginate_table(page, warnings)]
        pages = [item for page in pages for item in _paginate_comparison(page, warnings)]
        pages = [item for page in pages for item in _paginate_bullets(page, warnings)]
        prepared.extend(pages)
    if len(prepared) > 180:
        raise ValueError("自動拆頁後超過 180 張投影片；請先分拆教材，系統不會靜默截斷。")
    if not provenance_present:
        errors.append(_issue("PROVENANCE_MISSING", detail="缺少可追溯來源，禁止正式發布。", blocking=True))
    if not prepared:
        errors.append(_issue("NO_RENDERABLE_SLIDES", detail="沒有可產生的投影片。", blocking=True))
    for index, slide in enumerate(prepared, 1):
        slide["order"] = index
    manifest = sanitize_quality_manifest({
        "rulesetVersion": RULESET_VERSION,
        "slideCount": len(prepared),
        "warnings": warnings,
        "errors": errors,
    })
    return prepared, manifest


def add_warning(manifest: Mapping[str, Any], code: str, *, slide_id: str = "", detail: str = "") -> dict[str, Any]:
    payload = dict(manifest or {})
    warnings = list(payload.get("warnings") or [])
    warnings.append(_issue(code, slide_id=slide_id, detail=detail))
    payload["warnings"] = warnings
    return sanitize_quality_manifest(payload)


def regenerate_key(presentation: Mapping[str, Any]) -> str:
    snapshot = {
        "presentationId": str(presentation.get("id") or ""),
        "family": str(presentation.get("presentationFamilyId") or ""),
        "revision": int(presentation.get("revisionNumber") or 1),
        "templateId": str(presentation.get("templateId") or ""),
        "slides": list(presentation.get("slides") or []),
        "rulesetVersion": RULESET_VERSION,
    }
    canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "pptregen-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "RULESET_VERSION", "sanitize_quality_manifest", "sanitize_render_metrics",
    "sanitize_placeholder_map", "select_layout", "prepare_slides", "add_warning",
    "regenerate_key",
]
