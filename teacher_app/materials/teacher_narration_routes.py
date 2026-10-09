"""Teacher-recorded slide narration: bind an audio material to a slide material.

The teacher records narration while paging through a slide material in the
browser.  The audio travels through the normal browser -> R2 -> Worker upload
lane and becomes an ordinary audio material.  This module only *binds* that audio
to its source slide material together with a page timeline
(``[{"page": 0, "startMs": 0}, {"page": 1, "startMs": 8200}, ...]``) so the
learner viewer can turn pages in step with the voice.

No new table is needed: the binding lives in the audio material's
``storageMeta`` exactly like AI narration (``mediaKind`` + ``sourceMaterialId``),
which is what ``service._attach_narrations`` already folds into the source
material for learners.
"""
from __future__ import annotations

import datetime as dt
import json
from typing import Any, Mapping, Sequence

from flask import g, jsonify, request

from teacher_app.common import audit, scope_filter
from teacher_app.materials import repository as material_repository

MEDIA_KIND = "teacher_narration"
SLIDE_VIEWER_MODES = {"slides", "preview_pdf"}
MAX_TIMELINE_ENTRIES = 600
MAX_PAGE_INDEX = 2000
MAX_DURATION_MS = 4 * 60 * 60 * 1000


class TimelineError(ValueError):
    """The submitted page timeline is not usable."""


def normalize_timeline(raw: Any, *, page_count: int = 0, duration_ms: int = 0) -> list[dict[str, int]]:
    """Validate and clean a browser-supplied page timeline.

    * entries must be objects with integer ``page`` (0-based) and ``startMs``
    * ``startMs`` must not go backwards; the first entry is clamped to 0
    * consecutive entries for the same page are merged (the earliest start wins)
    * pages must exist in the source material when its page count is known
    """
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise TimelineError("翻頁時間表格式不正確。")
    if not raw:
        raise TimelineError("翻頁時間表是空的，請至少錄到一頁。")
    if len(raw) > MAX_TIMELINE_ENTRIES:
        raise TimelineError("翻頁次數過多，請縮短錄製或分段錄製。")
    cleaned: list[dict[str, int]] = []
    last_start = 0
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise TimelineError("翻頁時間表格式不正確。")
        try:
            page = int(item.get("page"))
            start = int(item.get("startMs"))
        except (TypeError, ValueError):
            raise TimelineError("翻頁時間表含有不是數字的頁碼或時間。") from None
        if page < 0 or page > MAX_PAGE_INDEX:
            raise TimelineError("翻頁時間表含有不合理的頁碼。")
        if page_count > 0 and page >= page_count:
            raise TimelineError(f"翻頁時間表指到第 {page + 1} 頁，但教材只有 {page_count} 頁。")
        if start < 0 or start > MAX_DURATION_MS:
            raise TimelineError("翻頁時間表含有不合理的時間。")
        if index == 0:
            start = 0
        if start < last_start:
            raise TimelineError("翻頁時間表的時間順序錯誤。")
        last_start = start
        if cleaned and cleaned[-1]["page"] == page:
            continue
        cleaned.append({"page": page, "startMs": start})
    if duration_ms > 0 and cleaned[-1]["startMs"] > duration_ms:
        raise TimelineError("翻頁時間超過錄音長度。")
    return cleaned


def _actor(owner=None):
    user = getattr(g, "teacher_user", None)
    if user is not None:
        return user
    resolver = getattr(owner, "_current_user", None)
    return resolver() if callable(resolver) else None


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def register_teacher_narration_routes(owner):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_narration_routes_registered"):
        return app

    @app.post("/api/materials/<source_id>/teacher-narration")
    def bind_teacher_narration(source_id):
        user = _actor(owner)
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        body = request.get_json(silent=True) or {}
        source_id = str(source_id or "").strip()
        audio_id = str(body.get("audioMaterialId") or "").strip()
        source = material_repository.get_material(source_id) if source_id else None
        audio = material_repository.get_material(audio_id) if audio_id else None
        if not source:
            return jsonify({"error": "找不到要配旁白的投影片教材。"}), 404
        if not audio:
            return jsonify({"error": "找不到剛上傳的旁白錄音教材。"}), 404
        if source_id == audio_id:
            return jsonify({"error": "旁白錄音不能掛在自己身上。"}), 400
        _user, denied = scope_filter.scoped_groups(
            owner, "material.manage", {str(source.get("group") or "").strip()}
        )
        if denied:
            return denied
        if (source.get("group"), source.get("area")) != (audio.get("group"), audio.get("area")):
            return jsonify({"error": "旁白錄音必須和投影片教材在同一組別與訓練區。"}), 400
        if str(source.get("viewerMode") or "") not in SLIDE_VIEWER_MODES:
            return jsonify({"error": "只有投影片或文件預覽類教材可以掛旁白。"}), 400
        if str(audio.get("viewerMode") or "") != "audio":
            return jsonify({"error": "旁白錄音必須是音訊教材。"}), 400
        audio_meta = dict(audio.get("storageMeta") or {})
        bound_to = str(audio_meta.get("sourceMaterialId") or "")
        if audio_meta.get("mediaKind") and audio_meta.get("mediaKind") != MEDIA_KIND:
            return jsonify({"error": "這份音訊教材已被其他功能使用，不能當作老師旁白。"}), 409
        if bound_to and bound_to != source_id:
            return jsonify({"error": "這份錄音已掛在另一份教材上。"}), 409
        try:
            duration_ms = max(0, min(MAX_DURATION_MS, int(body.get("durationMs") or 0)))
        except (TypeError, ValueError):
            return jsonify({"error": "錄音長度格式不正確。"}), 400
        try:
            timeline = normalize_timeline(
                body.get("timeline"),
                page_count=int(source.get("pageCount") or 0),
                duration_ms=duration_ms,
            )
        except TimelineError as exc:
            return jsonify({"error": str(exc)}), 400

        audio_meta.update(
            {
                "mediaKind": MEDIA_KIND,
                "sourceMaterialId": source_id,
                "sourceVersion": int(source.get("currentVersion") or 1),
                "timeline": timeline,
                "durationMs": duration_ms,
                "boundBy": str(user.get("username") or "") if isinstance(user, Mapping) else "",
                "boundAt": _now(),
            }
        )
        material_repository.update_material_storage(
            audio_id,
            backend=str(audio.get("storageBackend") or "local"),
            storage_key=str(audio.get("storageKey") or ""),
            slides_prefix=str(audio.get("slidesPrefix") or ""),
            storage_meta_json=json.dumps(audio_meta, ensure_ascii=False, separators=(",", ":")),
        )
        audit.record_event(
            actor=user,
            action="material.teacher_narration.bind",
            target_type="material",
            target_id=source_id,
            group=str(source.get("group") or ""),
            detail={"audioMaterialId": audio_id, "pages": len(timeline), "durationMs": duration_ms},
        )
        return jsonify(
            {
                "ok": True,
                "sourceMaterialId": source_id,
                "audioMaterialId": audio_id,
                "timeline": timeline,
                "durationMs": duration_ms,
            }
        )

    app.extensions["teacher_narration_routes_registered"] = True
    return app


__all__ = ["MEDIA_KIND", "TimelineError", "normalize_timeline", "register_teacher_narration_routes"]
