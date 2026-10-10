"""Case/scenario question type ("情境題").

One case description (the question text) followed by 2-6 follow-up steps.  Every
step is a single-choice question.  The whole question counts as correct only
when *every* step is answered correctly, which keeps it compatible with the
exam's one-point-per-question scoring and review records.

Stored in ``quiz_questions.answer_config`` (``correctIndex`` is server-only and
is removed from learner payloads by ``exams.grading.ANSWER_SECRET_FIELDS``)::

    {"steps": [{"prompt": "下一步應如何處置？",
                "options": ["重新採檢", "直接發報告"],
                "correctIndex": 0}]}

The learner answer is a list with one chosen option index (or ``null``) per step.
"""
from __future__ import annotations

from typing import Any, Mapping

SCENARIO_TYPE = "scenario"
MIN_STEPS = 2
MAX_STEPS = 6
MIN_OPTIONS = 2
MAX_OPTIONS = 6
MAX_PROMPT = 500
MAX_OPTION = 200


def prepare_config(answer_config: Mapping[str, Any] | None) -> dict:
    """Validate teacher input; raise ``ValueError`` with a readable message."""
    raw = answer_config.get("steps") if isinstance(answer_config, Mapping) else None
    if not isinstance(raw, list) or len(raw) < MIN_STEPS:
        raise ValueError(f"情境題至少需要 {MIN_STEPS} 個小問題")
    if len(raw) > MAX_STEPS:
        raise ValueError(f"情境題最多 {MAX_STEPS} 個小問題")
    steps: list[dict] = []
    for number, step in enumerate(raw, start=1):
        if not isinstance(step, Mapping):
            raise ValueError(f"第 {number} 個小問題格式不正確")
        prompt = str(step.get("prompt") or "").strip()[:MAX_PROMPT]
        if not prompt:
            raise ValueError(f"第 {number} 個小問題沒有題目")
        options_raw = step.get("options")
        if not isinstance(options_raw, list):
            raise ValueError(f"第 {number} 個小問題沒有選項")
        # Keep positions stable: the correct index refers to the list the
        # teacher saw, so blanks are rejected rather than silently removed.
        options = [str(value or "").strip()[:MAX_OPTION] for value in options_raw][:MAX_OPTIONS]
        if len(options) < MIN_OPTIONS or any(not value for value in options):
            raise ValueError(f"第 {number} 個小問題至少要有 {MIN_OPTIONS} 個選項，且選項不可空白")
        try:
            correct = int(step.get("correctIndex"))
        except (TypeError, ValueError):
            raise ValueError(f"第 {number} 個小問題請選擇正確答案") from None
        if not 0 <= correct < len(options):
            raise ValueError(f"第 {number} 個小問題的正確答案超出選項範圍")
        steps.append({"prompt": prompt, "options": options, "correctIndex": correct})
    return {"steps": steps}


def is_correct(answer_config: Any, answer: Any) -> bool:
    steps = answer_config.get("steps") if isinstance(answer_config, Mapping) else None
    if not isinstance(steps, list) or not steps or not isinstance(answer, list) or len(answer) != len(steps):
        return False
    for step, chosen in zip(steps, answer):
        if isinstance(chosen, bool):
            return False
        try:
            if int(chosen) != int(step.get("correctIndex", -1)):
                return False
        except (TypeError, ValueError, AttributeError):
            return False
    return True


def display_answer(answer: Any) -> str:
    if not isinstance(answer, list) or not answer:
        return "未答"
    letters = "ABCDEF"
    parts = []
    for index, chosen in enumerate(answer, start=1):
        try:
            value = int(chosen)
            parts.append(f"{index}.{letters[value] if 0 <= value < len(letters) else value + 1}")
        except (TypeError, ValueError):
            parts.append(f"{index}.未答")
    return "　".join(parts)
