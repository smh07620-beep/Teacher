"""Atlas "click the structure" (hotspot) question type.

A hotspot question points at one teacher-drawn mark on an Atlas image
(:mod:`teacher_app.atlas.annotations`).  The learner clicks on the image and the
server checks the click against the stored region.

Stored in ``quiz_questions.answer_config`` (all server-only; every key below is
removed from learner payloads by ``exams.grading.ANSWER_SECRET_FIELDS``)::

    {"atlasItemId": "...", "correctMarkId": "m1",
     "correctRegion": {"x":..,"y":..,"w":..,"h":..}, "markLabel": "嗜中性球"}

``correctRegion`` is a copy taken when the question is saved.  When an exam
attempt starts, :func:`resolve_for_attempt` refreshes it from the Atlas so that
a teacher who later corrects a box does not have to re-save every question; the
attempt then keeps its own immutable snapshot like any other question.
"""
from __future__ import annotations

from typing import Any, Mapping

from teacher_app.atlas import annotations
from teacher_app.atlas import repository as atlas_repository

HOTSPOT_TYPE = "atlas_hotspot"


def prepare_config(answer_config: Mapping[str, Any] | None) -> tuple[dict, str]:
    """Validate a teacher-supplied config.

    Returns ``(config, image_url)``.  Raises ``ValueError`` (the question
    routes turn that into HTTP 400) with a teacher-readable message.
    """
    config = dict(answer_config) if isinstance(answer_config, Mapping) else {}
    item_id = str(config.get("atlasItemId") or "").strip()[:100]
    mark_id = str(config.get("correctMarkId") or "").strip()[:60]
    if not item_id:
        raise ValueError("點選圖片題請先選擇一張圖譜")
    item = atlas_repository.get_item(item_id)
    if not item:
        raise ValueError("找不到指定的圖譜，可能已被刪除")
    if not item.get("published"):
        raise ValueError("這張圖譜尚未發布，學員看不到圖片。請先在圖譜區發布後再出題")
    if not mark_id:
        raise ValueError("請選擇要讓學員點出的標記")
    mark = annotations.find_mark(item.get("annotationJson"), mark_id)
    if not mark:
        raise ValueError("找不到指定的標記，請先在圖譜上框選細胞")
    image_url = str(item.get("imageUrl") or "").strip()
    if not image_url:
        raise ValueError("這張圖譜沒有圖片")
    config["atlasItemId"] = item_id
    config["correctMarkId"] = str(mark["id"])
    config["correctRegion"] = annotations.region_of(mark)
    config["markLabel"] = str(mark.get("label") or "")
    return config, image_url


def resolve_for_attempt(question: Mapping[str, Any]) -> dict:
    """Return the question with its region refreshed from the Atlas.

    Missing/deleted Atlas items keep the region saved with the question, so an
    exam never silently becomes ungradable.
    """
    result = dict(question)
    if str(result.get("questionType") or "") != HOTSPOT_TYPE:
        return result
    config = dict(result.get("answerConfig") or {}) if isinstance(result.get("answerConfig"), Mapping) else {}
    try:
        item = atlas_repository.get_item(str(config.get("atlasItemId") or ""))
    except Exception:
        item = {}
    mark = annotations.find_mark((item or {}).get("annotationJson"), str(config.get("correctMarkId") or ""))
    if mark:
        config["correctRegion"] = annotations.region_of(mark)
        config["markLabel"] = str(mark.get("label") or config.get("markLabel") or "")
    result["answerConfig"] = config
    return result


def is_correct(question: Mapping[str, Any], answer: Any) -> bool:
    config = question.get("answerConfig") if isinstance(question.get("answerConfig"), Mapping) else {}
    return annotations.point_in_region(answer, config.get("correctRegion"))


def display_answer(answer: Any) -> str:
    """Short, human-readable record of where the learner clicked."""
    if not isinstance(answer, Mapping):
        return "未答"
    try:
        return f"點選位置 ({float(answer['x']) * 100:.0f}%, {float(answer['y']) * 100:.0f}%)"
    except (KeyError, TypeError, ValueError):
        return "未答"
