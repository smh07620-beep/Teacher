"""Pure server-side exam grading and learner-safe question projection."""

from __future__ import annotations

from typing import Any, Mapping


def text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


ANSWER_SECRET_FIELDS = {
    "correct",
    "correctAnswer",
    "correctAnswers",
    "correctIndices",
    "acceptedAnswers",
    "answer",
    "answers",
    "answerKey",
    "answerKeys",
    "expectedAnswer",
    "expectedAnswers",
    "solution",
    "solutions",
    "explanation",
    "scoringKey",
    "scoringSecret",
    "gradingKey",
    "gradingSecret",
}


def strip_answer_secrets(value: Any) -> Any:
    """Recursively remove server-only answer/scoring fields."""
    if isinstance(value, Mapping):
        return {
            str(key): strip_answer_secrets(child)
            for key, child in value.items()
            if str(key) not in ANSWER_SECRET_FIELDS
        }

    if isinstance(value, list):
        return [
            strip_answer_secrets(child)
            for child in value
        ]

    return value


def sanitize_answer_config(config: Any) -> dict[str, Any]:
    """Learner-safe answer config for an unfinished attempt."""
    if not isinstance(config, dict):
        return {}

    safe = strip_answer_secrets(config)

    if not isinstance(safe, dict):
        return {}

    # Teacher 6.6 M4:
    # Review navigation is intentionally hidden until submission.
    safe.pop("reviewSource", None)

    return safe


def normalize_review_source(value: Any) -> dict[str, Any]:
    """Normalize safe post-exam learning navigation metadata."""
    if not isinstance(value, Mapping):
        return {}

    material_id = text(
        value.get("materialId"),
        200,
    )

    material_title = text(
        value.get("materialTitle"),
        500,
    )

    section = text(
        value.get("section"),
        1000,
    )

    review_hint = text(
        value.get("reviewHint"),
        2000,
    )

    region_hint = text(
        value.get("regionHint"),
        1000,
    )

    anchor_type = text(
        value.get("anchorType"),
        20,
    ).lower()

    if anchor_type not in {
        "page",
        "time",
        "region",
        "section",
    }:
        anchor_type = ""

    try:
        page = int(
            value.get("page") or 0
        )
    except (TypeError, ValueError):
        page = 0

    page = max(
        0,
        min(100000, page),
    )

    try:
        time_seconds = float(
            value.get("timeSeconds")
            or 0
        )
    except (TypeError, ValueError):
        time_seconds = 0.0

    time_seconds = max(
        0.0,
        min(
            86400.0,
            time_seconds,
        ),
    )

    if not anchor_type:
        if page:
            anchor_type = "page"
        elif time_seconds:
            anchor_type = "time"
        elif region_hint:
            anchor_type = "region"
        elif section or review_hint:
            anchor_type = "section"

    result: dict[str, Any] = {}

    if material_id:
        result["materialId"] = material_id

    if material_title:
        result["materialTitle"] = material_title

    if anchor_type:
        result["anchorType"] = anchor_type

    if page:
        result["page"] = page

    if time_seconds:
        result["timeSeconds"] = time_seconds

    if region_hint:
        result["regionHint"] = region_hint

    if section:
        result["section"] = section

    if review_hint:
        result["reviewHint"] = review_hint

    return result


def sanitize_question(question: Mapping[str, Any]) -> dict[str, Any]:
    """Return an unfinished-attempt question with no review/answer secrets."""
    safe = strip_answer_secrets(
        dict(question or {})
    )

    if not isinstance(safe, dict):
        return {}

    answer_config = safe.get(
        "answerConfig"
    )

    if isinstance(answer_config, dict):
        safe["answerConfig"] = (
            sanitize_answer_config(
                answer_config
            )
        )

    # Defensive support if future/imported questions use a top-level value.
    safe.pop(
        "reviewSource",
        None,
    )

    return safe


def review_question(
    question: Mapping[str, Any],
) -> dict[str, Any]:
    """Post-submission learner projection.

    Teacher explanations and all answer/scoring secrets remain private.
    Only safe learning-navigation metadata may be added after submission.
    """
    safe = sanitize_question(
        question
    )

    raw_config = question.get(
        "answerConfig"
    )

    if not isinstance(
        raw_config,
        Mapping,
    ):
        raw_config = {}

    source = normalize_review_source(
        raw_config.get(
            "reviewSource"
        )
        or question.get(
            "reviewSource"
        )
    )

    if source:
        safe["reviewSource"] = (
            source
        )

    return safe


def normalize_indices(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    result: list[int] = []
    for item in value:
        try:
            index = int(item)
        except (TypeError, ValueError):
            continue
        if index not in result:
            result.append(index)
    return sorted(result)


def score_question(question: Mapping[str, Any], answer: Any) -> bool | None:
    """Grade one answer. Essays return None for later human review."""
    question_type = str(question.get("questionType") or "choice")
    config = question.get("answerConfig") if isinstance(question.get("answerConfig"), dict) else {}
    if question_type == "essay":
        return None
    if question_type == "multi":
        return normalize_indices(config.get("correctIndices", [])) == normalize_indices(answer)
    if question_type == "fill":
        case_sensitive = bool(config.get("caseSensitive", False))
        actual = str(answer or "").strip()
        if not case_sensitive:
            actual = actual.casefold()
        for candidate in config.get("acceptedAnswers", []) or []:
            expected = str(candidate or "").strip()
            if not case_sensitive:
                expected = expected.casefold()
            if actual == expected:
                return True
        return False
    try:
        return int(answer) == int(question.get("correct", -999999))
    except (TypeError, ValueError):
        return False


def display_answer(question: Mapping[str, Any], answer: Any) -> str:
    question_type = str(question.get("questionType") or "choice")
    options = question.get("options") if isinstance(question.get("options"), list) else []
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    has_value = bool(answer) if isinstance(answer, list) else answer is not None and str(answer).strip() != ""
    if not has_value:
        return "未答"
    if question_type in {"essay", "fill"}:
        return text(answer, 12000)
    if question_type == "multi":
        return "、".join(letters[i] if 0 <= i < len(letters) else str(i + 1) for i in normalize_indices(answer))
    try:
        index = int(answer)
    except (TypeError, ValueError):
        return "未答"
    if question_type == "true_false" and 0 <= index < len(options):
        return text(options[index], 200)
    return letters[index] if 0 <= index < len(letters) else str(index + 1)


def grade_attempt(questions: list[dict[str, Any]], answers: list[Any], passing_score: int) -> dict[str, Any]:
    """Grade an immutable server-side question snapshot."""
    details: list[dict[str, Any]] = []
    correct_count = wrong_count = essay_count = 0
    category_stats: dict[str, dict[str, int]] = {}
    for index, question in enumerate(questions):
        answer = answers[index]
        question_type = str(question.get("questionType") or "choice")
        result = score_question(question, answer)
        tag = text(question.get("tag") or "一般", 100)
        details.append({"num": index + 1, "questionText": text(question.get("question"), 5000),
                        "questionType": question_type, "userAnswer": display_answer(question, answer),
                        "isCorrect": result})
        if question_type == "essay":
            essay_count += 1
            continue
        stats = category_stats.setdefault(tag, {"total": 0, "correct": 0})
        stats["total"] += 1
        if result is True:
            correct_count += 1
            stats["correct"] += 1
        else:
            wrong_count += 1
    total = len(questions)
    score = round((correct_count / total) * 100) if total else 0
    status = "待人工批改" if essay_count else ("合格" if score >= passing_score else "未達標")
    return {"answersDetail": details, "score": score, "status": status, "correctCount": correct_count,
            "wrongCount": wrong_count, "essayCount": essay_count, "categoryStats": category_stats}
