"""Canonical assessment blueprint creation and immutable snapshot publication."""
from __future__ import annotations

import datetime as dt
import json
import random
import uuid
from typing import Any, Mapping

from teacher_app.assessments import analytics as analytics_service
from teacher_app.assessments import repository
from teacher_app.common.errors import ApiError


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _decode(value: Any, fallback: Any) -> Any:
    try:
        return json.loads(value) if isinstance(value, str) else value
    except Exception:
        return fallback


def _draw(rows: list[dict], count: int, quotas: Mapping[str, Any], excluded=()) -> list[dict]:
    """Find one exact-sized set satisfying every quota dimension simultaneously."""
    excluded_ids = set(excluded)
    candidates = [row for row in rows if row.get("id") not in excluded_ids]
    if count < 1 or len(candidates) < count:
        raise ValueError("已審核題目不足以建立 blueprint")

    requirements: list[tuple[str, str, int]] = []
    for field in ("topic", "difficulty", "cognitive_level"):
        requested = quotas.get(field, {})
        if not isinstance(requested, dict):
            raise ValueError("quota 格式錯誤")
        for value, amount in requested.items():
            amount = int(amount or 0)
            if amount < 0 or amount > count:
                raise ValueError("quota 數量無效")
            if amount:
                requirements.append((field, str(value), amount))

    if any("_selectionWeight" in row for row in candidates):
        def weighted_key(row):
            try:
                weight = max(0.05, float(row.get("_selectionWeight", 1.0) or 1.0))
            except (TypeError, ValueError):
                weight = 1.0
            return random.random() ** (1.0 / weight)
        candidates.sort(key=weighted_key, reverse=True)
    else:
        random.shuffle(candidates)
    suffix = [[0] * len(requirements) for _ in range(len(candidates) + 1)]
    for index in range(len(candidates) - 1, -1, -1):
        suffix[index] = suffix[index + 1].copy()
        for requirement_index, (field, value, _amount) in enumerate(requirements):
            suffix[index][requirement_index] += (
                str(candidates[index].get(field) or "") == value
            )

    def search(index: int, picked: list[dict], counts: list[int]):
        if len(picked) == count:
            return (
                picked
                if all(
                    counts[j] >= need
                    for j, (_field, _value, need) in enumerate(requirements)
                )
                else None
            )
        if len(candidates) - index < count - len(picked):
            return None
        if any(
            counts[j] + suffix[index][j] < need
            for j, (_field, _value, need) in enumerate(requirements)
        ):
            return None

        row = candidates[index]
        next_counts = counts.copy()
        for j, (field, value, _need) in enumerate(requirements):
            next_counts[j] += str(row.get(field) or "") == value
        result = search(index + 1, picked + [row], next_counts)
        return result if result is not None else search(index + 1, picked, counts)

    result = search(0, [], [0] * len(requirements))
    if result is None:
        raise ValueError("無法同時滿足 topic、difficulty 與 cognitive quota")
    return result


def create_blueprint(data: Mapping[str, Any], *, username: str) -> dict:
    try:
        count = max(1, min(500, int(data.get("questionCount", 0) or 0)))
        exclude_recent = max(0, int(data.get("excludeRecent", 0) or 0))
    except (TypeError, ValueError):
        raise ApiError("BLUEPRINT_NUMBER_INVALID", "題數或排除次數格式錯誤", status=400)

    quotas = data.get("quotas") or {}
    if not isinstance(quotas, dict):
        raise ApiError("BLUEPRINT_QUOTAS_INVALID", "quotas 格式錯誤", status=400)
    quality_mode = str(data.get("qualityMode") or "off").strip().lower()
    if quality_mode not in {"off", "balanced"}:
        raise ApiError("BLUEPRINT_QUALITY_MODE_INVALID", "qualityMode 格式錯誤", status=400)
    stored_quotas = dict(quotas)
    stored_quotas["_selectionPolicy"] = {
        "mode": quality_mode,
        "version": analytics_service.SELECTION_POLICY_VERSION,
    }

    blueprint_id = str(uuid.uuid4())
    repository.insert_blueprint({
        "id": blueprint_id,
        "quiz_category_id": str(data.get("quizCategoryId") or ""),
        "question_count": count,
        "quotas": json.dumps(stored_quotas, ensure_ascii=False),
        "exclude_recent": exclude_recent,
        "created_by": username,
        "created_at": now(),
    })
    return {
        "id": blueprint_id,
        "questionCount": count,
        "qualityMode": quality_mode,
        "immutableSnapshotRequired": True,
    }


def publish_blueprint(blueprint_id: str) -> tuple[dict, int]:
    existing = repository.get_blueprint_snapshot(blueprint_id)
    if existing:
        return ({
            "id": existing["id"],
            "blueprintId": blueprint_id,
            "questions": _decode(existing.get("questions"), []),
            "createdAt": existing.get("created_at", ""),
            "immutable": True,
        }, 200)

    blueprint = repository.get_blueprint(blueprint_id)
    if not blueprint:
        raise ApiError("BLUEPRINT_NOT_FOUND", "找不到 blueprint", status=404)

    category_id = str(blueprint.get("quiz_category_id") or "")
    rows = repository.list_blueprint_questions(category_id)
    for row in rows:
        row["version"] = max(1, int(row.get("version", 1) or 1))
        row["questionHash"] = repository.question_content_hash(row)
    recent: set[str] = set()
    exclude_recent = int(blueprint.get("exclude_recent") or 0)
    if exclude_recent > 0:
        for snapshot in repository.list_recent_blueprint_snapshots(
            category_id,
            exclude_recent,
        ):
            for question in _decode(snapshot.get("questions"), []):
                if isinstance(question, dict):
                    recent.add(str(question.get("id") or ""))

    quotas = _decode(blueprint.get("quotas"), {})
    selection_policy = quotas.pop("_selectionPolicy", {}) if isinstance(quotas, dict) else {}
    quality_mode = str((selection_policy or {}).get("mode") or "off").lower()
    if quality_mode == "balanced":
        metrics_by_id: dict[str, dict] = {}
        for row in rows:
            metrics_by_id[str(row.get("id") or "")] = analytics_service.get_question_analytics(
                str(row.get("id") or ""),
                version=max(1, int(row.get("version", 1) or 1)),
            )
        max_exposure = max(
            [int(item.get("exposureCount", 0) or 0) for item in metrics_by_id.values()] or [0]
        )
        for row in rows:
            metrics = metrics_by_id.get(str(row.get("id") or ""), {})
            row["_selectionAnalytics"] = metrics
            row["_selectionWeight"] = analytics_service.balanced_selection_weight(
                metrics,
                max_exposure=max_exposure,
            )

    try:
        chosen = _draw(
            rows,
            int(blueprint.get("question_count") or 0),
            quotas if isinstance(quotas, dict) else {},
            recent,
        )
    except ValueError as exc:
        raise ApiError("BLUEPRINT_UNSATISFIABLE", str(exc), status=409)

    snapshot_id = str(uuid.uuid4())
    stamp = now()
    snapshot_questions = []
    for row in chosen:
        item = dict(row)
        weight = item.pop("_selectionWeight", None)
        metrics = item.pop("_selectionAnalytics", None)
        if quality_mode == "balanced":
            item["selection"] = {
                "mode": "balanced",
                "policyVersion": str(
                    (selection_policy or {}).get("version")
                    or analytics_service.SELECTION_POLICY_VERSION
                ),
                "weight": weight,
                "metrics": metrics or {},
            }
        snapshot_questions.append(item)
    repository.insert_blueprint_snapshot({
        "id": snapshot_id,
        "blueprint_id": blueprint_id,
        "quiz_category_id": category_id,
        "questions": json.dumps(snapshot_questions, ensure_ascii=False),
        "created_at": stamp,
    })
    return ({
        "id": snapshot_id,
        "blueprintId": blueprint_id,
        "questionCount": len(chosen),
        "qualityMode": quality_mode,
        "selectionPolicyVersion": str(
            (selection_policy or {}).get("version")
            or analytics_service.SELECTION_POLICY_VERSION
        ),
        "immutable": True,
        "createdAt": stamp,
    }, 201)
