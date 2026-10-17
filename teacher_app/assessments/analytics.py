"""Canonical Question Bank item analytics aggregation."""
from __future__ import annotations

from collections import Counter
import math

from teacher_app.assessments import repository


MIN_SUFFICIENT_ATTEMPTS = 10
SELECTION_POLICY_VERSION = "analytics-balanced-v1"


def get_question_analytics(question_id: str, *, version: int | None = None) -> dict:
    if version is None:
        identity = repository.current_question_version_identity(question_id)
        version = max(1, int(identity.get("version", 1) or 1))
        question_hash = str(identity.get("questionHash") or "")
    else:
        stored = repository.get_question_version(question_id, version)
        question_hash = str((stored or {}).get("question_hash") or "")
    rows = repository.list_question_attempt_analytics(
        question_id,
        version=version,
        question_hash=question_hash,
    )
    attempt_count = len(rows)
    if attempt_count < MIN_SUFFICIENT_ATTEMPTS:
        return {
            "attemptCount": attempt_count,
            "sufficientData": False,
            "message": "資料不足",
            "questionVersion": version,
            "questionHash": question_hash,
        }

    counts = dict(Counter(row.get("selected_option") for row in rows))
    correct = str(repository.get_question_version_correct(question_id, version) or "")
    correct_rate = sum(bool(row.get("is_correct")) for row in rows) / attempt_count
    scored = [
        row
        for row in rows
        if row.get("attempt_score") is not None
    ]
    discrimination = None
    if len(scored) >= MIN_SUFFICIENT_ATTEMPTS:
        ordered = sorted(scored, key=lambda row: float(row.get("attempt_score") or 0))
        group_size = max(1, int(math.ceil(len(ordered) * 0.27)))
        low = ordered[:group_size]
        high = ordered[-group_size:]
        discrimination = round(
            (sum(bool(row.get("is_correct")) for row in high) / len(high))
            - (sum(bool(row.get("is_correct")) for row in low) / len(low)),
            3,
        )
    timings = [
        float(row.get("response_seconds") or 0)
        for row in rows
        if row.get("response_seconds") is not None
        and float(row.get("response_seconds") or 0) > 0
    ]
    options = repository.get_question_version_options(question_id, version)
    distractor_keys = [str(index) for index in range(len(options)) if str(index) != correct]
    distractor_effectiveness = (
        round(
            sum(1 for key in distractor_keys if int(counts.get(key, 0) or 0) > 0)
            / len(distractor_keys),
            3,
        )
        if distractor_keys
        else None
    )
    return {
        "attemptCount": attempt_count,
        "exposureCount": attempt_count,
        "sufficientData": True,
        "questionVersion": version,
        "questionHash": question_hash,
        "correctRate": round(correct_rate, 3),
        "difficultyP": round(correct_rate, 3),
        "discriminationD": discrimination,
        "averageResponseSeconds": (
            round(sum(timings) / len(timings), 1)
            if timings
            else None
        ),
        "optionSelectionCounts": counts,
        "distractorDistribution": {
            key: value
            for key, value in counts.items()
            if str(key) != correct
        },
        "distractorEffectiveness": distractor_effectiveness,
    }


def balanced_selection_weight(metrics: dict, *, max_exposure: int = 0) -> float:
    """Return a bounded, explainable item-selection weight.

    This never excludes a reviewed item.  It only biases otherwise eligible
    candidates, and insufficient data remains neutral.
    """

    if not metrics.get("sufficientData"):
        return 1.0
    try:
        difficulty = float(metrics.get("difficultyP"))
    except (TypeError, ValueError):
        difficulty = 0.7
    try:
        discrimination = float(metrics.get("discriminationD"))
    except (TypeError, ValueError):
        discrimination = 0.0
    try:
        distractor = float(metrics.get("distractorEffectiveness"))
    except (TypeError, ValueError):
        distractor = 0.5
    exposure = max(0, int(metrics.get("exposureCount", 0) or 0))
    exposure_ceiling = max(1, int(max_exposure or exposure or 1))

    difficulty_fit = max(0.0, 1.0 - abs(difficulty - 0.7) / 0.7)
    discrimination_fit = max(0.0, min(1.0, (discrimination + 0.2) / 0.8))
    distractor_fit = max(0.0, min(1.0, distractor))
    freshness = max(0.0, min(1.0, 1.0 - (exposure / exposure_ceiling)))
    score = (
        0.30 * difficulty_fit
        + 0.35 * discrimination_fit
        + 0.15 * distractor_fit
        + 0.20 * freshness
    )
    return round(max(0.35, min(1.65, 0.65 + score)), 3)


def _flags(metrics: dict) -> list[dict]:
    """Plain-language findings a teacher can act on (empty when the item looks healthy)."""
    if not metrics.get("sufficientData"):
        return []
    found = []
    p = metrics.get("difficultyP")
    d = metrics.get("discriminationD")
    dist = metrics.get("distractorEffectiveness")
    if p is not None and p >= 0.9:
        found.append({"code": "too_easy", "label": "太簡單", "advice": "九成以上答對，可考慮加深或改成情境題。"})
    if p is not None and p < 0.3:
        found.append({"code": "too_hard", "label": "太難", "advice": "不到三成答對；請確認答案、題意或教材是否有教到。"})
    if d is not None and d < 0:
        found.append({"code": "reverse", "label": "高分者反而答錯", "advice": "成績好的人答錯比例較高，常見原因是答案設錯或題意有歧義，請優先檢查。"})
    elif d is not None and d < 0.2:
        found.append({"code": "low_discrimination", "label": "鑑別度低", "advice": "會的人和不會的人答對率差不多，題目可能只考記憶細節。"})
    if dist is not None and dist < 0.5:
        found.append({"code": "dead_distractor", "label": "選項沒人選", "advice": "一半以上的錯誤選項幾乎沒人選，請改成更像真的的選項。"})
    return found


def item_report(category_id: str) -> dict:
    """Health check of every active question in one exam, worst first."""
    questions = repository.list_questions(category_id, include_inactive=False)
    items = []
    for question in questions:
        qid = str(question.get("id") or "")
        if not qid:
            continue
        try:
            metrics = get_question_analytics(qid)
        except Exception:  # one broken item must not hide the rest
            metrics = {"attemptCount": 0, "sufficientData": False, "message": "讀取失敗"}
        flags = _flags(metrics)
        items.append({
            "questionId": qid,
            "question": str(question.get("question") or "")[:200],
            "questionType": str(question.get("questionType") or "choice"),
            "attemptCount": int(metrics.get("attemptCount") or 0),
            "sufficientData": bool(metrics.get("sufficientData")),
            "correctRate": metrics.get("correctRate"),
            "discriminationD": metrics.get("discriminationD"),
            "distractorEffectiveness": metrics.get("distractorEffectiveness"),
            "optionSelectionCounts": metrics.get("optionSelectionCounts") or {},
            "flags": flags,
        })
    severity = {"reverse": 0, "too_hard": 1, "dead_distractor": 2, "low_discrimination": 3, "too_easy": 4}
    items.sort(key=lambda it: (min((severity.get(f["code"], 9) for f in it["flags"]), default=10), -it["attemptCount"]))
    return {
        "categoryId": category_id,
        "minAttempts": MIN_SUFFICIENT_ATTEMPTS,
        "flaggedCount": sum(1 for it in items if it["flags"]),
        "insufficientCount": sum(1 for it in items if not it["sufficientData"]),
        "items": items,
    }
