"""Rules for optional in-slide checkpoint questions.

Opt-in by construction: a material with no checkpoint behaves exactly as before.
Teachers add checkpoints per material page; learners may answer or skip (never
blocks reading or completion).  The right answer and explanation reach a learner
only after a right answer or the second try (formative practice, not an exam).
"""
from __future__ import annotations

import datetime as dt
import json
import uuid
from typing import Any, Callable, Mapping

from teacher_app.checkpoints import repository, retry
from teacher_app.common.auth import has_permission, has_role, is_system_admin
from teacher_app.common.errors import ApiError
from teacher_app.learning import access as learning_access

MAX_PER_MATERIAL = 30
MAX_QUESTION = 500
MAX_OPTION = 200
MAX_EXPLANATION = 1500
MIN_OPTIONS = 2
MAX_OPTIONS = 6
MAX_PAGE = 5000
SLIDE_VIEWER_MODES = {"slides", "preview_pdf"}
MEDIA_VIEWER_MODES = {"video", "audio"}  # checkpoint "page" = the second it pauses at
MAX_MEDIA_SECOND = 6 * 3600

MaterialGetter = Callable[[str], Mapping[str, Any] | None]


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _username(user: Mapping[str, Any]) -> str:
    return str(user.get("username") or "")


def _fail(code: str, message: str, status: int = 400) -> ApiError:
    return ApiError(code, message, status=status)


def can_manage(user: Mapping[str, Any], material: Mapping[str, Any]) -> bool:
    if not has_permission(user, "material.manage"):
        return False
    if is_system_admin(user) or has_role(user, "education_admin"):
        return True
    preferred = str(user.get("preferredGroup") or user.get("preferred_group") or "")
    return preferred == str(material.get("group") or "")


def _material(get_material: MaterialGetter, material_id: str) -> Mapping[str, Any]:
    material = get_material(str(material_id or ""))
    if not material or not material.get("active", True):
        raise _fail("MATERIAL_NOT_FOUND", "找不到這份教材。", 404)
    return material


def _manageable_material(user, get_material, material_id):
    material = _material(get_material, material_id)
    if not can_manage(user, material):
        raise _fail("CHECKPOINT_FORBIDDEN", "無權設定這份教材的小測驗。", 403)
    return material


def manageable_material(user, get_material, material_id):
    """Public guard for the per-material reading rules (same rule as checkpoints)."""
    return _manageable_material(user, get_material, material_id)


def _readable_material(user, get_material, material_id):
    material = _material(get_material, material_id)
    if not learning_access.can_access_learning_item(user, material):
        raise _fail("MATERIAL_NOT_FOUND", "找不到這份教材。", 404)
    return material


def _clean(body: Mapping[str, Any], material: Mapping[str, Any]) -> dict:
    mode = str(material.get("viewerMode") or "")
    if mode not in SLIDE_VIEWER_MODES | MEDIA_VIEWER_MODES:
        raise _fail("CHECKPOINT_NOT_SLIDES", "只有投影片／PDF 或影音教材可以設定小測驗。")
    if mode in MEDIA_VIEWER_MODES:
        try:
            page = int(body.get("second", body.get("page")))
        except (TypeError, ValueError):
            raise _fail("CHECKPOINT_PAGE", "請填寫影片播放到第幾秒時出題。") from None
        if page < 1 or page > MAX_MEDIA_SECOND:
            raise _fail("CHECKPOINT_PAGE", "秒數必須介於 1 到 21600（6 小時）。")
    else:
        try:
            page = int(body.get("page"))
        except (TypeError, ValueError):
            raise _fail("CHECKPOINT_PAGE", "請填寫要在第幾頁出現。") from None
        total = int(material.get("pageCount") or 0)
        if page < 1 or page > (total or MAX_PAGE):
            raise _fail("CHECKPOINT_PAGE", f"頁碼必須介於 1 到 {total or MAX_PAGE}。")
    question = str(body.get("question") or "").strip()[:MAX_QUESTION]
    if not question:
        raise _fail("CHECKPOINT_QUESTION", "請填寫小測驗題目。")
    raw_options = body.get("options")
    if not isinstance(raw_options, list):
        raise _fail("CHECKPOINT_OPTIONS", "請填寫選項。")
    options = [str(value or "").strip()[:MAX_OPTION] for value in raw_options][:MAX_OPTIONS]
    if len(options) < MIN_OPTIONS or any(not value for value in options):
        raise _fail("CHECKPOINT_OPTIONS", f"至少要有 {MIN_OPTIONS} 個選項，且選項之間不可空白。")
    try:
        correct = int(body.get("correctIndex"))
    except (TypeError, ValueError):
        raise _fail("CHECKPOINT_CORRECT", "請選擇正確答案。") from None
    if not 0 <= correct < len(options):
        raise _fail("CHECKPOINT_CORRECT", "正確答案超出選項範圍。")
    return {
        "page_no": page,
        "question": question,
        "options": options,
        "correct_index": correct,
        "explanation": str(body.get("explanation") or "").strip()[:MAX_EXPLANATION],
    }


def create(user, get_material: MaterialGetter, material_id: str, body: Mapping[str, Any]) -> dict:
    material = _manageable_material(user, get_material, material_id)
    clean = _clean(body, material)
    if len(repository.list_for_material(material["id"])) >= MAX_PER_MATERIAL:
        raise _fail("CHECKPOINT_LIMIT", f"每份教材最多 {MAX_PER_MATERIAL} 題小測驗。")
    stamp = _now()
    checkpoint_id = "cp-" + uuid.uuid4().hex[:16]
    repository.insert({
        "id": checkpoint_id,
        "material_id": str(material["id"]),
        "material_version": int(material.get("currentVersion") or 1),
        "group_key": str(material.get("group") or ""),
        "page_no": clean["page_no"],
        "question": clean["question"],
        "options_json": json.dumps(clean["options"], ensure_ascii=False),
        "correct_index": clean["correct_index"],
        "explanation": clean["explanation"],
        "active": 1,
        "created_by": _username(user), "created_at": stamp,
        "updated_by": _username(user), "updated_at": stamp,
    })
    return repository.get(checkpoint_id)


def update(user, get_material: MaterialGetter, checkpoint_id: str, body: Mapping[str, Any]) -> dict:
    existing = repository.get(checkpoint_id)
    if not existing:
        raise _fail("CHECKPOINT_NOT_FOUND", "找不到這題小測驗。", 404)
    material = _manageable_material(user, get_material, existing["materialId"])
    changes: dict[str, Any] = {}
    if "active" in body:
        changes["active"] = 1 if body.get("active") else 0
    if any(key in body for key in ("page", "question", "options", "correctIndex", "explanation")):
        merged = {
            "page": existing["page"], "question": existing["question"], "options": existing["options"],
            "correctIndex": existing["correctIndex"], "explanation": existing["explanation"],
        }
        merged.update({key: body[key] for key in merged if key in body})
        clean = _clean(merged, material)
        changes.update({
            "page_no": clean["page_no"], "question": clean["question"],
            "options_json": json.dumps(clean["options"], ensure_ascii=False),
            "correct_index": clean["correct_index"], "explanation": clean["explanation"],
            # Editing re-targets the question to the material's current version.
            "material_version": int(material.get("currentVersion") or 1),
        })
    if changes:
        changes["updated_by"] = _username(user)
        changes["updated_at"] = _now()
        repository.update(checkpoint_id, changes)
    return repository.get(checkpoint_id)


def delete(user, get_material: MaterialGetter, checkpoint_id: str) -> None:
    existing = repository.get(checkpoint_id)
    if not existing:
        raise _fail("CHECKPOINT_NOT_FOUND", "找不到這題小測驗。", 404)
    _manageable_material(user, get_material, existing["materialId"])
    repository.delete(checkpoint_id)


def list_for_manager(user, get_material: MaterialGetter, material_id: str) -> dict:
    material = _manageable_material(user, get_material, material_id)
    stats = repository.answer_stats(material["id"])
    current = int(material.get("currentVersion") or 1)
    items = []
    for item in repository.list_for_material(material["id"]):
        item = dict(item)
        item["stale"] = item["materialVersion"] != current
        item["stats"] = stats.get(item["id"], {"answered": 0, "correct": 0})
        items.append(item)
    return {"items": items, "pageCount": int(material.get("pageCount") or 0)}


def _learner_view(item: Mapping[str, Any], answer: Mapping[str, Any] | None, second: Mapping[str, Any] | None = None) -> dict:
    """Two-stage reveal: a first wrong answer gets the explanation and one more try;
    the right option is shown only after a right answer or the second try."""
    view = {"id": item["id"], "page": item["page"], "question": item["question"], "options": list(item["options"])}
    if not answer:
        view["answered"] = False
        return view
    view["answered"] = True
    view["firstCorrect"] = bool(answer["isCorrect"])
    view["explanation"] = item["explanation"]
    if answer["isCorrect"]:
        view.update(attempts=1, canRetry=False, isCorrect=True, chosenIndex=answer["chosenIndex"], correctIndex=item["correctIndex"])
    elif second:
        view.update(attempts=2, canRetry=False, isCorrect=bool(second.get("isCorrect")),
                    chosenIndex=int(second.get("chosenIndex", -1)), firstChosenIndex=answer["chosenIndex"],
                    correctIndex=item["correctIndex"])
    else:
        view.update(attempts=1, canRetry=True, isCorrect=False, chosenIndex=answer["chosenIndex"])
    return view


def learner_items(user, material: Mapping[str, Any]) -> list[dict]:
    """Learner-safe checkpoint items for an already-authorised material."""
    from teacher_app.checkpoints import reading_rules

    if not reading_rules.checkpoints_enabled(material):
        return []
    current = int(material.get("currentVersion") or 1)
    answers = repository.answers_for_user(_username(user), material["id"])
    seconds = retry.retries_for(_username(user), material["id"]) if answers else {}
    items = [
        _learner_view(item, answers.get(item["id"]), seconds.get(item["id"]))
        for item in repository.list_for_material(material["id"])
        if item["active"] and item["materialVersion"] == current
    ]
    return items


def list_for_learner(user, get_material: MaterialGetter, material_id: str) -> dict:
    material = _readable_material(user, get_material, material_id)
    return {"items": learner_items(user, material)}


def answer(user, get_material: MaterialGetter, checkpoint_id: str, body: Mapping[str, Any]) -> dict:
    if has_role(user, "auditor") and not has_permission(user, "material.manage"):
        raise _fail("CHECKPOINT_READ_ONLY", "稽核帳號為唯讀，無法作答。", 403)
    item = repository.get(checkpoint_id)
    if not item or not item["active"]:
        raise _fail("CHECKPOINT_NOT_FOUND", "找不到這題小測驗。", 404)
    material = _readable_material(user, get_material, item["materialId"])
    if item["materialVersion"] != int(material.get("currentVersion") or 1):
        raise _fail("CHECKPOINT_NOT_FOUND", "找不到這題小測驗。", 404)
    chosen = body.get("chosenIndex")
    if isinstance(chosen, bool):
        raise _fail("CHECKPOINT_CHOICE", "請選擇一個答案。")
    try:
        chosen = int(chosen)
    except (TypeError, ValueError):
        raise _fail("CHECKPOINT_CHOICE", "請選擇一個答案。") from None
    if not 0 <= chosen < len(item["options"]):
        raise _fail("CHECKPOINT_CHOICE", "選項超出範圍。")
    correct = chosen == item["correctIndex"]
    username = _username(user)
    first = repository.get_answer(item["id"], username)
    if not first:
        # First answer is the learning record.  A wrong checkpoint never locks the
        # exam: the reader lists its page as 建議再看 instead (plan: 不影響通過).
        repository.record_answer(item["id"], username, item["materialId"], chosen, correct, _now())
    elif not first["isCorrect"]:
        try:
            retry.record(username, item["materialId"], item["id"], chosen, correct)
        except Exception:  # practice only: an unsaved retry must not break answering
            pass
    second = retry.retries_for(username, item["materialId"]).get(item["id"])
    return _learner_view(item, repository.get_answer(item["id"], username), second)
