"""Phase 6 quality, idempotency, and render metrics for AI presentation videos."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

RULESET_VERSION = "video-phase6-v1"
_MAX_ISSUES = 60
_MAX_RENDERER_ATTEMPTS = 8


def _clean(value: Any, limit: int = 500) -> str:
    return " ".join(str(value or "").replace("\x00", " ").split())[:limit]


def _issue(code: str, *, detail: str = "", slide_id: str = "", blocking: bool = False) -> dict[str, Any]:
    return {
        "code": _clean(code, 80),
        "detail": _clean(detail, 500),
        "slideId": _clean(slide_id, 120),
        "blocking": bool(blocking),
    }


def sanitize_quality_manifest(value: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(value or {})
    warnings = []
    errors = []
    for source, target, blocking in (
        (payload.get("warnings"), warnings, False),
        (payload.get("errors"), errors, True),
    ):
        for raw in list(source or [])[:_MAX_ISSUES]:
            if not isinstance(raw, Mapping):
                continue
            code = _clean(raw.get("code"), 80)
            if not code:
                continue
            target.append(
                _issue(
                    code,
                    detail=raw.get("detail"),
                    slide_id=raw.get("slideId"),
                    blocking=bool(raw.get("blocking", blocking)),
                )
            )
    status = "error" if errors else ("warning" if warnings else "ok")
    return {
        "rulesetVersion": _clean(payload.get("rulesetVersion") or RULESET_VERSION, 40),
        "status": status,
        "slideCount": max(0, min(500, int(payload.get("slideCount") or 0))),
        "warningCount": len(warnings),
        "errorCount": len(errors),
        "warnings": warnings,
        "errors": errors,
    }


def _renderer_attempts(value: Any) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for raw in list(value or [])[:_MAX_RENDERER_ATTEMPTS]:
        if not isinstance(raw, Mapping):
            continue
        renderer = _clean(raw.get("renderer"), 80)
        status = _clean(raw.get("status"), 40)
        if not renderer or not status:
            continue
        output.append(
            {
                "renderer": renderer,
                "status": status,
                "detail": _clean(raw.get("detail"), 160),
            }
        )
    return output


def sanitize_render_metrics(value: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(value or {})

    def integer(name: str, upper: int = 10**9) -> int:
        try:
            result = int(payload.get(name) or 0)
        except (TypeError, ValueError):
            result = 0
        return max(0, min(upper, result))

    return {
        "rulesetVersion": _clean(payload.get("rulesetVersion") or RULESET_VERSION, 40),
        "durationMs": integer("durationMs"),
        "attempts": integer("attempts", 100),
        "renderedSlideCount": integer("renderedSlideCount", 500),
        "ttsSegmentCount": integer("ttsSegmentCount", 500),
        "ffmpegSegmentCount": integer("ffmpegSegmentCount", 500),
        "frameRenderer": _clean(payload.get("frameRenderer"), 80),
        "rendererAttempts": _renderer_attempts(payload.get("rendererAttempts")),
        "jobId": _clean(payload.get("jobId"), 120),
    }


def add_warning(manifest: Mapping[str, Any], code: str, *, detail: str = "", slide_id: str = "") -> dict[str, Any]:
    payload = dict(manifest or {})
    warnings = list(payload.get("warnings") or [])
    warnings.append(_issue(code, detail=detail, slide_id=slide_id))
    payload["warnings"] = warnings
    return sanitize_quality_manifest(payload)


def add_error(manifest: Mapping[str, Any], code: str, *, detail: str = "", slide_id: str = "") -> dict[str, Any]:
    payload = dict(manifest or {})
    errors = list(payload.get("errors") or [])
    errors.append(_issue(code, detail=detail, slide_id=slide_id, blocking=True))
    payload["errors"] = errors
    return sanitize_quality_manifest(payload)


def evaluate_render(*, prepared_slides: list[Mapping[str, Any]], timeline: list[Mapping[str, Any]],
                    vtt_text: str, srt_text: str, frame_renderer: str,
                    presentation_sha256: str) -> dict[str, Any]:
    manifest = sanitize_quality_manifest({"rulesetVersion": RULESET_VERSION, "slideCount": len(prepared_slides)})
    if len(str(presentation_sha256 or "")) != 64:
        manifest = add_error(manifest, "SOURCE_CHECKSUM_MISSING", detail="來源 PowerPoint checksum 不完整。")
    if not prepared_slides:
        manifest = add_error(manifest, "NO_RENDERABLE_SLIDES", detail="沒有可產生影片的投影片。")
    if len(timeline) != len(prepared_slides):
        manifest = add_error(
            manifest,
            "TIMELINE_COUNT_MISMATCH",
            detail=f"時間軸 {len(timeline)} 段與投影片 {len(prepared_slides)} 張不一致。",
        )
    cursor = 0.0
    for index, entry in enumerate(timeline, 1):
        try:
            start = float(entry.get("start") or 0)
            end = float(entry.get("end") or 0)
        except (TypeError, ValueError):
            start = end = -1
        if start < -0.001 or end <= start or abs(start - cursor) > 0.08:
            manifest = add_error(
                manifest,
                "TIMELINE_INVALID",
                detail=f"第 {index} 段時間軸不連續或長度無效。",
                slide_id=str(entry.get("slideId") or ""),
            )
            break
        cursor = end
    if not str(vtt_text or "").lstrip().startswith("WEBVTT") or "-->" not in str(vtt_text or ""):
        manifest = add_error(manifest, "VTT_MISSING", detail="WebVTT 字幕未完整產生。")
    if "-->" not in str(srt_text or ""):
        manifest = add_error(manifest, "SRT_MISSING", detail="SRT 字幕未完整產生。")

    renderer = _clean(frame_renderer, 80)
    if renderer == "libreoffice-headless":
        manifest = add_warning(
            manifest,
            "FRAME_RENDERER_COMPATIBILITY",
            detail="PowerPoint COM 不可用或未成功，已由 LibreOffice headless 完整匯出投影片；字型與排版相容性請於發布前預覽確認。",
        )
    elif renderer == "text-fallback":
        manifest = add_warning(
            manifest,
            "FRAME_RENDERER_FALLBACK",
            detail="PowerPoint 與 LibreOffice 都未能完成投影片匯出，已改用安全文字畫面；發布前必須人工確認。",
        )
    elif renderer != "powerpoint-com":
        manifest = add_error(
            manifest,
            "FRAME_RENDERER_UNKNOWN",
            detail="影片使用了未列入允許清單的投影片 renderer。",
        )
    return sanitize_quality_manifest(manifest)


def generation_key(presentation: Mapping[str, Any], *, voice: str) -> str:
    snapshot = {
        "presentationId": str(presentation.get("id") or ""),
        "presentationFamilyId": str(presentation.get("presentationFamilyId") or ""),
        "revisionNumber": int(presentation.get("revisionNumber") or 1),
        "presentationSha256": str(presentation.get("artifactSha256") or ""),
        "voice": _clean(voice, 80),
        "rulesetVersion": RULESET_VERSION,
    }
    canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "vidgen-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "RULESET_VERSION",
    "add_error",
    "add_warning",
    "evaluate_render",
    "generation_key",
    "sanitize_quality_manifest",
    "sanitize_render_metrics",
]
