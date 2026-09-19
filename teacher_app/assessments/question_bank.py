"""Canonical Question Bank 2.0 CRUD and review behavior.

Question Bank rows live in the assessment schema, so this module deliberately
stays inside ``teacher_app.assessments`` instead of creating a parallel domain.
Blueprint snapshot and analytics ownership are migrated in later bounded slices.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import uuid
from typing import Any, Mapping

from teacher_app.assessments import repository
from teacher_app.common.errors import ApiError


VALID = {
    "difficulty": {"easy", "medium", "hard", "standard"},
    "cognitive_level": {"remember", "understand", "apply", "analyze"},
    "status": {"draft", "reviewed", "published", "retired"},
    "origin": {"manual", "ai_generated", "imported"},
}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalized(value: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", str(value).lower())).strip()


def similarity(left: Any, right: Any) -> float:
    x = set(normalized(left).split())
    y = set(normalized(right).split())
    return len(x & y) / max(1, len(x | y))


def metadata(data: Mapping[str, Any]) -> dict:
    aliases = {
        "learning_objective": "learningObjective",
        "source_material_id": "sourceMaterialId",
        "review_source": "reviewSource",
        "cognitive_level": "cognitiveLevel",
    }
    out = {
        key: (data[aliases[key]] if aliases.get(key) in data else data.get(key, ""))
        for key in (
            "domain", "topic", "subtopic", "learning_objective",
            "source_material_id", "review_source",
        )
    }
    for key, default in (
        ("difficulty", "medium"),
        ("cognitive_level", "understand"),
        ("status", "draft"),
        ("origin", "manual"),
    ):
        out[key] = str(data[aliases[key]] if aliases.get(key) in data else data.get(key, default))
        if out[key] not in VALID[key]:
            raise ApiError("QUESTION_BANK_METADATA_INVALID", f"{key} 格式錯誤", status=400)
    out["tags"] = data.get("tags", [])
    if not isinstance(out["tags"], list):
        raise ApiError("QUESTION_BANK_TAGS_INVALID", "tags 格式錯誤", status=400)
    return out


def _decode(value: Any, fallback: Any) -> Any:
    try:
        return json.loads(value) if isinstance(value, str) else value
    except Exception:
        return fallback


def question_payload(row: Mapping[str, Any]) -> dict:
    item = dict(row)
    for key, fallback in (("options", []), ("tags", []), ("review_source", {})):
        item[key] = _decode(item.get(key), fallback)
    item["quizCategoryId"] = item.pop("quiz_category_id", "") or ""
    item["questionType"] = item.pop("question_type", "choice") or "choice"
    item["learningObjective"] = item.pop("learning_objective", "") or ""
    item["cognitiveLevel"] = item.pop("cognitive_level", "understand") or "understand"
    item["sourceMaterialId"] = item.pop("source_material_id", "") or ""
    item["reviewSource"] = item.pop("review_source", {}) or {}
    item["updatedAt"] = item.pop("updated_at", "") or ""
    item["reviewedAt"] = item.pop("reviewed_at", "") or ""
    item["reviewedBy"] = item.pop("reviewed_by", "") or ""
    item["active"] = bool(item.get("active", True))
    return item


def create_draft(data: Mapping[str, Any]) -> dict:
    bank_meta = metadata(data)
    text = str(data.get("question") or "").strip()
    options = data.get("options")
    if not text or not isinstance(options, list):
        raise ApiError("QUESTION_BANK_REQUIRED", "題目與選項為必填", status=400)
    # This endpoint is deliberately a draft-only entry point.  Review state is
    # server-owned and may only advance through ``review_question``.
    bank_meta["status"] = "draft"

    question_id = str(uuid.uuid4())
    normalized_hash = hashlib.sha256(normalized(text).encode()).hexdigest()
    duplicates = []
    for row in repository.list_duplicate_candidates():
        score = similarity(text, row.get("question"))
        if row.get("normalized_hash") == normalized_hash or score >= 0.85:
            duplicates.append({"id": row.get("id"), "similarity": round(score, 2)})

    repository.insert_bank_question({
        "id": question_id,
        "quiz_category_id": str(data.get("quizCategoryId") or ""),
        "tag": str(data.get("tag") or ""),
        "question": text,
        "question_type": str(data.get("questionType") or "choice"),
        "options": json.dumps(options, ensure_ascii=False),
        "correct": int(data.get("correct", 0) or 0),
        "explanation": str(data.get("explanation") or ""),
        "domain": bank_meta["domain"],
        "topic": bank_meta["topic"],
        "subtopic": bank_meta["subtopic"],
        "learning_objective": bank_meta["learning_objective"],
        "difficulty": bank_meta["difficulty"],
        "cognitive_level": bank_meta["cognitive_level"],
        "tags": json.dumps(bank_meta["tags"], ensure_ascii=False),
        "source_material_id": bank_meta["source_material_id"],
        "review_source": json.dumps(bank_meta["review_source"], ensure_ascii=False),
        "status": bank_meta["status"],
        "origin": bank_meta["origin"],
        "updated_at": now(),
        "normalized_hash": normalized_hash,
    })
    return {
        "id": question_id,
        "status": bank_meta["status"],
        "suspectedDuplicates": duplicates,
    }


def list_questions(*, category_id: str = "", status: str = "") -> list[dict]:
    return [
        question_payload(row)
        for row in repository.list_bank_questions(category_id=category_id, status=status)
    ]


def update_question(question_id: str, data: Mapping[str, Any]) -> dict:
    existing = repository.get_bank_question(question_id)
    if not existing:
        raise ApiError("QUESTION_BANK_NOT_FOUND", "找不到題目", status=404)
    merged = {**existing, **dict(data)}
    # Ordinary edits invalidate a previous review.  Do not allow a browser to
    # promote a question by PATCHing ``status`` or rewrite its provenance.
    merged["status"] = "draft"
    merged["origin"] = existing.get("origin", "manual")
    bank_meta = metadata(merged)
    question = str(merged.get("question") or "").strip()
    options = merged.get("options")
    if not question or not isinstance(options, list):
        raise ApiError("QUESTION_BANK_REQUIRED", "題目與選項為必填", status=400)
    row = repository.update_bank_question(question_id, {
        "question": question,
        "options": json.dumps(options, ensure_ascii=False),
        "correct": int(merged.get("correct", 0) or 0),
        "explanation": str(merged.get("explanation") or ""),
        "topic": bank_meta["topic"],
        "subtopic": bank_meta["subtopic"],
        "learning_objective": bank_meta["learning_objective"],
        "difficulty": bank_meta["difficulty"],
        "cognitive_level": bank_meta["cognitive_level"],
        "tags": json.dumps(bank_meta["tags"], ensure_ascii=False),
        "source_material_id": bank_meta["source_material_id"],
        "review_source": json.dumps(bank_meta["review_source"], ensure_ascii=False),
        "status": bank_meta["status"],
        "origin": bank_meta["origin"],
        "updated_at": now(),
        "reviewed_by": "",
        "reviewed_at": "",
    })
    return {"ok": True, "item": question_payload(row or {})}


def delete_question(question_id: str) -> dict:
    return {"ok": repository.delete_bank_question(question_id)}


def review_question(question_id: str, *, decision: str, username: str) -> dict:
    decision = str(decision or "")
    if decision not in {"accept", "reject", "return"}:
        raise ApiError("QUESTION_BANK_REVIEW_INVALID", "decision 格式錯誤", status=400)
    return {
        "ok": repository.review_bank_question(
            question_id,
            decision=decision,
            username=str(username or ""),
            stamp=now(),
        )
    }
