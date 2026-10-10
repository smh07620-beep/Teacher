"""Text helpers for AI narration: per-slide segments, Taiwan wording, pronunciation.

Three small, pure helpers shared by the script generator and the AI Worker:

* ``split_script_segments`` -- cut an approved script into one spoken segment per
  paragraph (the script generator is told "paragraph k = slide k").
* ``apply_taiwan_terms`` -- replace a few unambiguous Mainland-only words in the
  *written* script with the wording used in Taiwanese hospitals.
* ``apply_pronunciation`` -- rewrite abbreviations, units and symbols into the
  words that should be *spoken*.  It is applied only right before speech synthesis,
  so slides, scripts and subtitles keep the original text.  The editable table is
  ``tts_pronunciation_table.json`` next to this file.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

PLACEHOLDER = "【需教師補充】"
TABLE_PATH = Path(__file__).with_name("tts_pronunciation_table.json")

# Only wording that is unambiguous in a medical-laboratory script.  Ambiguous
# words (e.g. 質量, 樣本, 標本) are deliberately left to the teacher.
TAIWAN_TERM_FIXES: tuple[tuple[str, str], ...] = (
    ("室內質控", "內部品質管制"),
    ("室間質評", "能力試驗"),
    ("質量控制", "品質管制"),
    ("質量管理", "品質管理"),
    ("質控", "品管"),
    ("信息", "資訊"),
    ("軟件", "軟體"),
    ("硬件", "硬體"),
    ("網絡", "網路"),
    ("數據庫", "資料庫"),
    ("服務器", "伺服器"),
    ("默認", "預設"),
    ("打印", "列印"),
    ("視頻", "影片"),
)


def apply_taiwan_terms(text: str) -> str:
    """Replace Mainland-only wording in a written script (longest phrase first)."""
    value = str(text or "")
    for source, target in sorted(TAIWAN_TERM_FIXES, key=lambda pair: -len(pair[0])):
        value = value.replace(source, target)
    return value


def split_script_segments(body: str) -> list[str]:
    """One segment per blank-line separated paragraph, without the review note.

    Lines starting with ``※`` (the teacher-review disclosure) are never spoken.
    A paragraph that is only the "需教師補充" placeholder becomes an empty
    segment, so the slide keeps its place but nothing is read aloud for it.
    """
    segments: list[str] = []
    for block in re.split(r"\n\s*\n", str(body or "").replace("\r\n", "\n").replace("\r", "\n")):
        lines = [line.strip() for line in block.split("\n") if line.strip() and not line.strip().startswith("※")]
        if not lines:
            if block.strip() and not block.strip().startswith("※"):
                segments.append("")
            continue
        text = " ".join(lines).strip()
        segments.append("" if text == PLACEHOLDER else text)
    return segments


@lru_cache(maxsize=1)
def _compiled_table() -> tuple[list[tuple[re.Pattern, str]], re.Pattern | None, dict[str, str]]:
    try:
        table: dict[str, Any] = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        table = {}
    regex_rules: list[tuple[re.Pattern, str]] = []
    for rule in table.get("regex") or []:
        try:
            regex_rules.append((re.compile(str(rule["pattern"])), str(rule["say"])))
        except (KeyError, re.error, TypeError):
            continue
    terms: dict[str, str] = {}
    for rule in table.get("terms") or []:
        match, say = str(rule.get("match") or ""), str(rule.get("say") or "")
        if match and say:
            terms[match] = say
    if not terms:
        return regex_rules, None, {}
    alternatives = []
    for match in sorted(terms, key=lambda item: (-len(item), item)):
        prefix = r"(?<![A-Za-z0-9])" if re.match(r"[A-Za-z0-9]", match) else ""
        suffix = r"(?![A-Za-z0-9])" if re.search(r"[A-Za-z0-9]$", match) else ""
        alternatives.append(f"{prefix}{re.escape(match)}{suffix}")
    return regex_rules, re.compile("|".join(alternatives)), terms


def apply_pronunciation(text: str) -> str:
    """Return the text to *speak* (display text is never changed by this)."""
    value = str(text or "")
    regex_rules, term_pattern, terms = _compiled_table()
    for pattern, say in regex_rules:
        value = pattern.sub(say, value)
    if term_pattern is not None:
        value = term_pattern.sub(lambda found: terms.get(found.group(0), found.group(0)), value)
    return value


__all__ = [
    "PLACEHOLDER",
    "TAIWAN_TERM_FIXES",
    "apply_pronunciation",
    "apply_taiwan_terms",
    "split_script_segments",
]
