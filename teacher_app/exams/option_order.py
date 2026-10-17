"""Per-attempt option shuffling (2026-10-17).

Each learner sees the options of choice / multi questions in their own order so
neighbours cannot copy "選 B".  The attempt snapshot keeps the teacher's
original order plus ``optionOrder``; answers are mapped back to the original
indices before grading, so records, analytics and teacher views never change.
"""
from __future__ import annotations

import random
import re
from typing import Any, Mapping

SHUFFLE_TYPES = {"choice", "multi"}
# Options that only make sense in a fixed position ("以上皆是", "none of the above").
_POSITIONAL = re.compile(r"以上|皆是|皆非|都對|都不對|上述|all of the above|none of the above|both a", re.I)


def _option_text(option: Any) -> str:
    if isinstance(option, Mapping):
        return str(option.get("text") or option.get("label") or "")
    return str(option or "")


def can_shuffle(question: Mapping[str, Any]) -> bool:
    if str(question.get("questionType") or "choice") not in SHUFFLE_TYPES:
        return False
    options = question.get("options")
    if not isinstance(options, list) or len(options) < 3:
        return False
    return not any(_POSITIONAL.search(_option_text(option)) for option in options)


def assign(questions: list[dict[str, Any]], *, enabled: bool = True, rng: random.Random | None = None) -> list[dict[str, Any]]:
    """Store a random ``optionOrder`` on every shuffle-able question (snapshot keeps original options)."""
    rng = rng or random
    for question in questions:
        question.pop("optionOrder", None)
        if enabled and can_shuffle(question):
            order = list(range(len(question["options"])))
            rng.shuffle(order)
            if order != sorted(order):
                question["optionOrder"] = order
    return questions


def _order(question: Mapping[str, Any]) -> list[int] | None:
    order = question.get("optionOrder")
    options = question.get("options")
    if not isinstance(order, list) or not isinstance(options, list) or sorted(order) != list(range(len(options))):
        return None
    return [int(i) for i in order]


def present(question: Mapping[str, Any]) -> dict[str, Any]:
    """Learner-facing copy: options in the shuffled order, no ``optionOrder`` key."""
    safe = dict(question)
    order = _order(question)
    safe.pop("optionOrder", None)
    if order:
        safe["options"] = [question["options"][i] for i in order]
    return safe


def to_original(question: Mapping[str, Any], answer: Any) -> Any:
    """Map an answer given against the shown order back to the teacher's order."""
    order = _order(question)
    if not order:
        return answer
    qtype = str(question.get("questionType") or "choice")
    try:
        if qtype == "multi" and isinstance(answer, list):
            return sorted(order[int(i)] for i in answer if 0 <= int(i) < len(order))
        if answer is None or str(answer).strip() == "":
            return answer
        index = int(answer)
        return order[index] if 0 <= index < len(order) else answer
    except (TypeError, ValueError):
        return answer
