"""Spread the correct answers of AI-generated choice questions evenly over A-D.

Language models strongly favour putting the right answer at "B".  Asking them
to randomise in the prompt does not help, so the positions are rearranged here
after generation.  Questions whose wording depends on the option order (for
example "以上皆是", "A 和 B", "選項 C") or whose options are a natural numeric
sequence are left exactly as the model wrote them.
"""
from __future__ import annotations

import random
import re
from typing import Any, Iterable

# Wording that only makes sense with the original option order.
_ORDER_DEPENDENT = re.compile(
    r"以上|上述|前述|上列|下列皆|皆是|皆非|皆正確|皆錯|皆不|都是|都不是|均是|均非|全部正確|全部錯誤"
    r"|[（(][A-Da-d][)）]|選項\s*[A-Da-d]|答案\s*[是為]?\s*[A-Da-d](?![A-Za-z])"
    r"|(?<![A-Za-z])[A-D]\s*[和及與、,，]\s*[A-D](?![A-Za-z])"
)
_LEADING_NUMBER = re.compile(r"\s*[<>≤≥≦≧±~約]*\s*(-?\d+(?:\.\d+)?)")


def _text_values(question: dict) -> Iterable[str]:
    yield str(question.get("question") or "")
    yield str(question.get("explanation") or "")
    for option in question.get("options") or []:
        yield str(option)


def _depends_on_order(question: dict) -> bool:
    return any(_ORDER_DEPENDENT.search(text) for text in _text_values(question))


def _is_natural_numeric_order(options: list[str]) -> bool:
    numbers: list[float] = []
    for option in options:
        match = _LEADING_NUMBER.match(option)
        if not match:
            return False
        numbers.append(float(match.group(1)))
    if len(set(numbers)) != len(numbers):
        return False
    return numbers == sorted(numbers) or numbers == sorted(numbers, reverse=True)


def _can_move(question: dict) -> bool:
    if question.get("questionType") not in {"choice", "multi"}:
        return False
    options = question.get("options")
    if not isinstance(options, list) or len(options) != 4:
        return False
    if len({str(option).strip() for option in options}) != 4:
        return False
    if _depends_on_order(question) or _is_natural_numeric_order([str(option) for option in options]):
        return False
    return True


def _place_single(question: dict, target: int, rng: random.Random) -> None:
    options = list(question["options"])
    try:
        correct = int(question.get("correct", 0))
    except (TypeError, ValueError):
        return
    if not 0 <= correct < 4:
        return
    others = [option for index, option in enumerate(options) if index != correct]
    rng.shuffle(others)
    question["options"] = others[:target] + [options[correct]] + others[target:]
    question["correct"] = target


def _place_multi(question: dict, rng: random.Random) -> None:
    config = question.get("answerConfig") if isinstance(question.get("answerConfig"), dict) else {}
    indices = [index for index in (config.get("correctIndices") or []) if isinstance(index, int) and 0 <= index < 4]
    if not indices:
        return
    order = [0, 1, 2, 3]
    rng.shuffle(order)
    options = list(question["options"])
    question["options"] = [options[old] for old in order]
    new_index = {old: new for new, old in enumerate(order)}
    mapped = sorted(new_index[index] for index in set(indices))
    config["correctIndices"] = mapped
    question["answerConfig"] = config
    question["correct"] = mapped[0]


def balance_answer_positions(questions: list[dict], rng: random.Random | None = None) -> int:
    """Rearrange options in place; return how many questions were moved.

    Single-answer questions get target positions from repeated shuffled A-D
    rounds, so a batch of 8 has every letter exactly twice.
    """
    rng = rng or random.Random()
    singles = [q for q in questions if q.get("questionType") == "choice" and _can_move(q)]
    multis = [q for q in questions if q.get("questionType") == "multi" and _can_move(q)]
    targets: list[int] = []
    while len(targets) < len(singles):
        block = [0, 1, 2, 3]
        rng.shuffle(block)
        targets.extend(block)
    for question, target in zip(singles, targets):
        _place_single(question, target, rng)
    for question in multis:
        _place_multi(question, rng)
    return len(singles) + len(multis)


__all__ = ["balance_answer_positions"]
