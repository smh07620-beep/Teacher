"""Canonical runtime quiz-question mutation helpers.

These helpers preserve the long-lived quiz-question payload shape while keeping
database ownership in :mod:`teacher_app.assessments.repository`.
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Mapping

from teacher_app.assessments import repository
from teacher_app.common import db as common_db


QUESTION_TYPES = {"choice", "essay", "multi", "fill", "image", "video", "true_false"}
OPTION_TYPES = {"choice", "multi", "image", "video", "true_false"}


def mark_category_draft(category_id: str, conn=None, kind: str | None = None) -> None:
    category_id = str(category_id or "").strip()
    if not category_id:
        return
    if conn is not None:
        repository.mark_category_draft_on_connection(conn, kind, category_id)
        return
    repository.mark_category_draft(category_id)


def _clean_review_source(value: Any) -> dict:
    if not isinstance(value, dict):
        return {}
    out: dict[str, Any] = {}
    for source_key, target_key, limit in (
        ("materialId", "materialId", 200),
        ("materialTitle", "materialTitle", 500),
        ("regionHint", "regionHint", 1000),
        ("section", "section", 1000),
        ("reviewHint", "reviewHint", 2000),
    ):
        text = str(value.get(source_key, "") or "").strip()[:limit]
        if text:
            out[target_key] = text

    anchor_type = str(value.get("anchorType", "") or "").strip().lower()[:20]
    if anchor_type in {"page", "time", "region", "section"}:
        out["anchorType"] = anchor_type

    try:
        page = max(0, min(100000, int(value.get("page", 0) or 0)))
    except Exception:
        page = 0
    if page:
        out["page"] = page

    try:
        time_seconds = max(0.0, min(86400.0, float(value.get("timeSeconds", 0) or 0)))
    except Exception:
        time_seconds = 0.0
    if time_seconds:
        out["timeSeconds"] = time_seconds
    return out


def _normalized_common(data: Mapping[str, Any], *, existing: Mapping[str, Any] | None = None) -> dict:
    existing = existing or {}
    question = str(data.get("question", existing.get("question", ""))).strip()
    question_type = str(data.get("questionType", existing.get("questionType", "choice"))).lower()
    if question_type not in QUESTION_TYPES:
        question_type = "choice"
    image_url = str(data.get("imageUrl", existing.get("imageUrl", ""))).strip()[:1000]
    options = data.get("options", existing.get("options", []))
    answer_config = data.get("answerConfig", existing.get("answerConfig", {}))
    answer_config = dict(answer_config) if isinstance(answer_config, dict) else {}

    if question_type in {"essay", "fill"}:
        options = []
    if question_type == "true_false":
        options = ["是", "否"]
    if question_type in OPTION_TYPES and (not isinstance(options, list) or len(options) < 2):
        raise ValueError("此題型至少需要 2 個選項")
    options = [str(value).strip() for value in options][:6]

    if question_type == "multi":
        answer_config["correctIndices"] = sorted(
            set(
                int(value)
                for value in answer_config.get("correctIndices", [])
                if str(value).lstrip("-").isdigit()
            )
        )
        if not answer_config["correctIndices"]:
            raise ValueError("多選題至少要設定一個正確選項")
    if question_type == "fill":
        answer_config["acceptedAnswers"] = [
            str(value).strip()
            for value in answer_config.get("acceptedAnswers", [])
            if str(value).strip()
        ][:20]
        answer_config["caseSensitive"] = bool(answer_config.get("caseSensitive", False))
        if not answer_config["acceptedAnswers"]:
            raise ValueError("填空題至少要設定一個可接受答案")
    if question_type == "video":
        answer_config["mediaUrl"] = str(answer_config.get("mediaUrl", "")).strip()[:1500]
        try:
            answer_config["pauseAt"] = max(0, float(answer_config.get("pauseAt", 0) or 0))
        except Exception:
            answer_config["pauseAt"] = 0

    tag = str(data.get("tag", existing.get("tag", ""))).strip()[:100] or "一般"
    difficulty = str(data.get("difficulty", existing.get("difficulty", "standard")) or "standard").lower()
    if difficulty not in {"basic", "standard", "advanced"}:
        difficulty = "standard"
    explanation = str(data.get("explanation", existing.get("explanation", ""))).strip()
    try:
        correct = int(data.get("correct", existing.get("correct", 0)))
    except (TypeError, ValueError):
        correct = int(existing.get("correct", 0) or 0)
    correct = max(0, min(len(options) - 1, correct)) if options else 0
    if not question:
        raise ValueError("題目內容不能空白")
    return {
        "question": question,
        "questionType": question_type,
        "imageUrl": image_url,
        "options": options,
        "correct": correct,
        "answerConfig": answer_config,
        "tag": tag,
        "difficulty": difficulty,
        "explanation": explanation,
        "active": bool(data.get("active", existing.get("active", True))),
    }


def prepare_question_update(entry: Mapping[str, Any], data: Mapping[str, Any]) -> dict:
    return _normalized_common(data if isinstance(data, dict) else {}, existing=entry)


def create_question(data: Mapping[str, Any]) -> dict:
    category_id = str(data.get("quizCategoryId", "")).strip()
    if not repository.get_category_full(category_id):
        raise ValueError("找不到對應的考題頁籤，請先建立頁籤")

    # Preserve the create endpoint's legacy wording for incomplete option types.
    question = str(data.get("question", "")).strip()
    question_type = str(data.get("questionType", "choice")).lower()
    if question_type not in QUESTION_TYPES:
        question_type = "choice"
    raw_options = data.get("options", [])
    if question_type in {"essay", "fill"}:
        raw_options = []
    if question_type == "true_false":
        raw_options = ["是", "否"]
    if not question or (question_type in OPTION_TYPES and (not isinstance(raw_options, list) or len(raw_options) < 2)):
        raise ValueError("請輸入題目；選擇／多選／圖片／影片題至少需要 2 個選項")

    normalized = _normalized_common({**dict(data), "questionType": question_type, "options": raw_options})
    review_source = _clean_review_source(normalized["answerConfig"].get("reviewSource"))
    if review_source:
        normalized["answerConfig"]["reviewSource"] = review_source
    else:
        normalized["answerConfig"].pop("reviewSource", None)

    question_id = f"q-{uuid.uuid4().hex[:12]}"
    with common_db.transaction() as (conn, kind):
        next_order = repository.next_question_sort_order(conn, kind, category_id)
        repository.insert_runtime_question_on_connection(
            conn,
            kind,
            {
                "id": question_id,
                "quiz_category_id": category_id,
                "tag": normalized["tag"],
                "question": normalized["question"],
                "question_type": normalized["questionType"],
                "difficulty": normalized["difficulty"],
                "image_url": normalized["imageUrl"],
                "options": json.dumps(normalized["options"], ensure_ascii=False),
                "correct": normalized["correct"],
                "answer_config": json.dumps(normalized["answerConfig"], ensure_ascii=False),
                "explanation": normalized["explanation"],
                "sort_order": next_order,
                "active": True,
            },
        )
        mark_category_draft(category_id, conn, kind)
    return repository.get_question(question_id) or {"id": question_id, **normalized}


def update_question(question_id: str, data: Mapping[str, Any]) -> dict:
    entry = repository.get_question(question_id)
    if not entry:
        raise LookupError("找不到此題目")
    normalized = prepare_question_update(entry, data)
    with common_db.transaction() as (conn, kind):
        repository.update_runtime_question_on_connection(conn, kind, question_id, normalized)
        mark_category_draft(entry.get("quizCategoryId"), conn, kind)
    return {"ok": True, "question": {"id": question_id, **normalized}}


def batch_update(items: Any) -> dict:
    if not isinstance(items, list) or not items:
        raise ValueError("items 必須是非空陣列")
    if len(items) > 200:
        raise ValueError("一次最多更新 200 題")
    requested: list[str] = []
    patches: dict[str, dict] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        question_id = str(item.get("id", "")).strip()
        if not question_id or question_id in patches:
            continue
        requested.append(question_id)
        patches[question_id] = (
            item.get("data")
            if isinstance(item.get("data"), dict)
            else {key: value for key, value in item.items() if key != "id"}
        )
    if not requested:
        raise ValueError("沒有有效題目")

    with common_db.transaction() as (conn, kind):
        existing = repository.get_questions_by_ids_on_connection(conn, kind, requested)
        missing = [question_id for question_id in requested if question_id not in existing]
        if missing:
            return {"missing": missing}
        normalized_items = []
        for question_id in requested:
            try:
                normalized = prepare_question_update(existing[question_id], patches[question_id])
            except ValueError as exc:
                raise ValueError(f"題目 {question_id}：{exc}") from exc
            normalized_items.append((question_id, normalized))
        for question_id, normalized in normalized_items:
            repository.update_runtime_question_on_connection(conn, kind, question_id, normalized)
        for category_id in {
            str(existing[question_id].get("quizCategoryId", "")) for question_id in requested
        }:
            mark_category_draft(category_id, conn, kind)
    return {
        "ok": True,
        "updated": [{"id": question_id, **normalized} for question_id, normalized in normalized_items],
        "count": len(normalized_items),
        "reviewInvalidated": True,
    }


def batch_delete(ids: Any) -> dict:
    question_ids = (
        list(dict.fromkeys(str(value).strip() for value in ids if str(value).strip()))
        if isinstance(ids, list)
        else []
    )
    if not question_ids:
        raise ValueError("ids 必須是非空陣列")
    if len(question_ids) > 200:
        raise ValueError("一次最多刪除 200 題")
    with common_db.transaction() as (conn, kind):
        category_ids = repository.delete_questions_on_connection(conn, kind, question_ids)
        for category_id in category_ids:
            mark_category_draft(category_id, conn, kind)
    return {
        "ok": True,
        "deleted": question_ids,
        "count": len(question_ids),
        "reviewInvalidated": True,
    }


def delete_question(question_id: str) -> dict:
    entry = repository.get_question(question_id)
    if not entry:
        raise LookupError("找不到此題目")
    with common_db.transaction() as (conn, kind):
        repository.delete_questions_on_connection(conn, kind, [question_id])
        mark_category_draft(entry.get("quizCategoryId"), conn, kind)
    return {"ok": True}


def insert_payload(category_id: str, payload: Mapping[str, Any]) -> str:
    qtext = str(payload.get("question", "")).strip()
    qtype = str(payload.get("questionType", "choice")).lower()
    if qtype not in QUESTION_TYPES:
        qtype = "choice"
    config = dict(payload.get("answerConfig")) if isinstance(payload.get("answerConfig"), dict) else {}
    options = [str(value).strip() for value in (payload.get("options") or []) if str(value).strip()][:6]
    if qtype in {"essay", "fill"}:
        options = []
    if qtype == "true_false":
        options = ["是", "否"]
    if not qtext or (qtype in OPTION_TYPES and len(options) < 2):
        raise ValueError("題目內容或選項不足")
    try:
        correct = int(payload.get("correct", 0) or 0)
    except Exception:
        correct = 0
    correct = max(0, min(len(options) - 1, correct)) if options else 0
    if qtype == "multi":
        indices = []
        for value in config.get("correctIndices", []) or []:
            try:
                index = int(value)
                if 0 <= index < len(options):
                    indices.append(index)
            except Exception:
                pass
        indices = sorted(set(indices))
        if not indices:
            raise ValueError("多選題至少要設定一個正確選項")
        config["correctIndices"] = indices
        correct = indices[0]
    if qtype == "fill":
        answers = [str(value).strip() for value in config.get("acceptedAnswers", []) if str(value).strip()][:20]
        if not answers:
            raise ValueError("填空題至少要設定一個可接受答案")
        config["acceptedAnswers"] = answers
        config["caseSensitive"] = bool(config.get("caseSensitive", False))
    if config.get("mediaUrl"):
        config["mediaUrl"] = str(config.get("mediaUrl"))[:1500]
        try:
            config["pauseAt"] = max(0, float(config.get("pauseAt", 0) or 0))
        except Exception:
            config["pauseAt"] = 0
    difficulty = str(payload.get("difficulty", "standard") or "standard").lower()
    if difficulty not in {"basic", "standard", "advanced"}:
        difficulty = "standard"
    question_id = f"q-{uuid.uuid4().hex[:12]}"
    with common_db.transaction() as (conn, kind):
        order = repository.next_question_sort_order(conn, kind, category_id)
        repository.insert_runtime_question_on_connection(
            conn,
            kind,
            {
                "id": question_id,
                "quiz_category_id": category_id,
                "tag": str(payload.get("tag", ""))[:100],
                "question": qtext[:2000],
                "question_type": qtype,
                "difficulty": difficulty,
                "image_url": str(payload.get("imageUrl", ""))[:1000],
                "options": json.dumps(options, ensure_ascii=False),
                "correct": correct,
                "answer_config": json.dumps(config, ensure_ascii=False),
                "explanation": str(payload.get("explanation", ""))[:4000],
                "sort_order": order,
                "active": True,
            },
        )
    return question_id


def insert_payloads_bulk(category_id: str, items: list[Mapping[str, Any]]) -> list[dict]:
    prepared = []
    for payload in items:
        if not isinstance(payload, dict):
            raise ValueError("題目格式錯誤")
        qtext = str(payload.get("question", "")).strip()
        qtype = str(payload.get("questionType", "choice")).lower()
        if qtype not in QUESTION_TYPES:
            qtype = "choice"
        config = dict(payload.get("answerConfig")) if isinstance(payload.get("answerConfig"), dict) else {}
        raw_options = payload.get("options") or []
        if qtype in OPTION_TYPES and qtype != "true_false" and not isinstance(raw_options, list):
            raise ValueError("選項格式錯誤")
        options = [str(value).strip() for value in raw_options if str(value).strip()][:6] if isinstance(raw_options, list) else []
        if qtype in {"essay", "fill"}:
            options = []
        if qtype == "true_false":
            options = ["是", "否"]
        if not qtext or (qtype in OPTION_TYPES and len(options) < 2):
            raise ValueError("題目內容或選項不足")
        try:
            correct = int(payload.get("correct", 0) or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("正確答案格式錯誤") from exc
        if qtype in {"choice", "image", "video", "true_false"} and not 0 <= correct < len(options):
            raise ValueError("正確答案超出選項範圍")
        correct = correct if options else 0
        if qtype == "multi":
            raw_indices = config.get("correctIndices", [])
            if not isinstance(raw_indices, list):
                raise ValueError("多選題正確選項格式錯誤")
            indices = []
            invalid_index = False
            for value in raw_indices:
                try:
                    index = int(value)
                    if 0 <= index < len(options):
                        indices.append(index)
                    else:
                        invalid_index = True
                except Exception:
                    invalid_index = True
            if invalid_index:
                raise ValueError("多選題正確選項超出選項範圍")
            indices = sorted(set(indices))
            if not indices:
                raise ValueError("多選題至少要設定一個正確選項")
            config["correctIndices"] = indices
            correct = indices[0]
        if qtype == "fill":
            raw_answers = config.get("acceptedAnswers", [])
            if not isinstance(raw_answers, list):
                raise ValueError("填空題可接受答案格式錯誤")
            answers = [str(value).strip() for value in raw_answers if str(value).strip()][:20]
            if not answers:
                raise ValueError("填空題至少要設定一個可接受答案")
            config["acceptedAnswers"] = answers
            config["caseSensitive"] = bool(config.get("caseSensitive", False))
        if config.get("mediaUrl"):
            config["mediaUrl"] = str(config.get("mediaUrl"))[:1500]
            try:
                config["pauseAt"] = max(0, float(config.get("pauseAt", 0) or 0))
            except Exception:
                config["pauseAt"] = 0
        difficulty = str(payload.get("difficulty", "standard") or "standard").lower()
        if difficulty not in {"basic", "standard", "advanced"}:
            difficulty = "standard"
        prepared.append(
            {
                "id": f"q-{uuid.uuid4().hex[:12]}",
                "quizCategoryId": category_id,
                "tag": str(payload.get("tag", ""))[:100],
                "question": qtext[:2000],
                "questionType": qtype,
                "difficulty": difficulty,
                "imageUrl": str(payload.get("imageUrl", ""))[:1000],
                "options": options,
                "correct": correct,
                "answerConfig": config,
                "explanation": str(payload.get("explanation", ""))[:4000],
                "active": True,
            }
        )
    if not prepared:
        return []
    with common_db.transaction() as (conn, kind):
        order = repository.next_question_sort_order(conn, kind, category_id)
        for index, question in enumerate(prepared):
            question["sortOrder"] = order + index
            repository.insert_runtime_question_on_connection(
                conn,
                kind,
                {
                    "id": question["id"],
                    "quiz_category_id": category_id,
                    "tag": question["tag"],
                    "question": question["question"],
                    "question_type": question["questionType"],
                    "difficulty": question["difficulty"],
                    "image_url": question["imageUrl"],
                    "options": json.dumps(question["options"], ensure_ascii=False),
                    "correct": question["correct"],
                    "answer_config": json.dumps(question["answerConfig"], ensure_ascii=False),
                    "explanation": question["explanation"],
                    "sort_order": question["sortOrder"],
                    "active": True,
                },
            )
    return prepared
