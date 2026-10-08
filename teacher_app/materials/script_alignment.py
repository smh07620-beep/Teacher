"""Automatically align an approved lecture script to PowerPoint slides.

Teachers should never have to pick cut points. The script is split into natural
units (paragraphs, then lines, then sentences) and the units are assigned to the
slides *in order* by dynamic programming. A unit scores higher on the slide whose
title/bullets share more distinctive character bigrams with it; a small balance
penalty keeps one slide from swallowing the whole script. No AI call is needed,
so the result is deterministic, free and safe to run inside the Web request.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Mapping, Sequence

NOTES_LIMIT = 4000
CHARS_PER_MINUTE = 280  # same pace the script generator is asked to target
_MAX_UNITS = 240
_BALANCE_WEIGHT = 0.15
_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?；;])\s*")
_DISCLOSURE = re.compile(r"^\s*※.*$")


def split_units(body: str, slide_count: int) -> list[str]:
    """Split a script into natural units, finer only when there are too few."""
    text = str(body or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    units = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if len(units) < slide_count:
        units = [line.strip() for line in text.split("\n") if line.strip()]
    if len(units) < slide_count:
        units = [part.strip() for part in _SENTENCE_SPLIT.split(text) if part.strip()]
    # The generator's closing "※ 需由教師確認" disclosure is not narration.
    units = [unit for unit in units if not _DISCLOSURE.match(unit)]
    if len(units) > _MAX_UNITS:  # merge neighbours instead of dropping content
        size = math.ceil(len(units) / _MAX_UNITS)
        units = ["\n".join(units[i:i + size]) for i in range(0, len(units), size)]
    return units


def _grams(text: str) -> set[str]:
    compact = re.sub(r"\s+", "", str(text or "").lower())
    if len(compact) < 2:
        return {compact} if compact else set()
    return {compact[i:i + 2] for i in range(len(compact) - 1)}


def slide_text(slide: Mapping[str, Any]) -> str:
    parts = [str(slide.get("title") or "")]
    parts.extend(str(item) for item in list(slide.get("bullets") or []))
    for block in list(slide.get("blocks") or []):
        if isinstance(block, Mapping):
            for key in ("text", "caption", "leftTitle", "rightTitle"):
                if block.get(key):
                    parts.append(str(block.get(key)))
            for key in ("leftItems", "rightItems", "headers", "labels"):
                parts.extend(str(item) for item in list(block.get(key) or []))
    return " ".join(part for part in parts if part)


def _similarity_matrix(units: Sequence[str], slides: Sequence[Mapping[str, Any]]) -> list[list[float]]:
    slide_grams = [_grams(slide_text(slide)) for slide in slides]
    document_frequency: Counter[str] = Counter()
    for grams in slide_grams:
        document_frequency.update(grams)
    count = max(1, len(slides))

    def weight(gram: str) -> float:
        return math.log(1 + count / max(1, document_frequency.get(gram, 0) or 1))

    slide_norm = [math.sqrt(sum(weight(g) ** 2 for g in grams)) or 1.0 for grams in slide_grams]
    matrix: list[list[float]] = []
    for unit in units:
        grams = _grams(unit)
        unit_norm = math.sqrt(sum(weight(g) ** 2 for g in grams)) or 1.0
        row = []
        for index, other in enumerate(slide_grams):
            shared = grams & other
            dot = sum(weight(g) ** 2 for g in shared)
            row.append(dot / (unit_norm * slide_norm[index]) if shared else 0.0)
        matrix.append(row)
    return matrix


def align_script_to_slides(body: str, slides: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Return one narration segment per slide, in slide order.

    ``slides`` should be only the slides that will actually be shown. The result
    always has ``len(slides)`` segments; a slide may be empty only when the script
    has fewer units than there are slides.
    """
    slide_count = len(slides)
    segments = [""] * slide_count
    units = split_units(body, slide_count) if slide_count else []
    if not units:
        return {"segments": segments, "unitCount": 0, "mode": "empty"}
    unit_count = len(units)
    sim = _similarity_matrix(units, slides)
    lengths = [len(re.sub(r"\s+", "", unit)) for unit in units]
    prefix_len = [0]
    for length in lengths:
        prefix_len.append(prefix_len[-1] + length)
    ideal = max(1.0, prefix_len[-1] / slide_count)
    prefix_sim = [[0.0] * (unit_count + 1) for _ in range(slide_count)]
    for s in range(slide_count):
        for i in range(unit_count):
            prefix_sim[s][i + 1] = prefix_sim[s][i] + sim[i][s]

    sparse = unit_count < slide_count  # each unit gets its own slide, some slides stay empty
    min_group = 0 if sparse else 1
    max_group = 1 if sparse else unit_count
    negative_infinity = float("-inf")
    best = [[negative_infinity] * (unit_count + 1) for _ in range(slide_count + 1)]
    choice = [[0] * (unit_count + 1) for _ in range(slide_count + 1)]
    best[0][0] = 0.0
    for s in range(1, slide_count + 1):
        for i in range(unit_count + 1):
            for size in range(min_group, min(max_group, i) + 1):
                previous = best[s - 1][i - size]
                if previous == negative_infinity:
                    continue
                start = i - size
                score = prefix_sim[s - 1][i] - prefix_sim[s - 1][start]
                if not sparse:
                    chars = prefix_len[i] - prefix_len[start]
                    score -= _BALANCE_WEIGHT * ((chars - ideal) / ideal) ** 2
                total = previous + score
                if total > best[s][i]:
                    best[s][i] = total
                    choice[s][i] = size
    if best[slide_count][unit_count] == negative_infinity:  # defensive: cannot happen by construction
        per = math.ceil(unit_count / slide_count)
        for s in range(slide_count):
            segments[s] = "\n".join(units[s * per:(s + 1) * per])
        return {"segments": segments, "unitCount": unit_count, "mode": "even"}
    i = unit_count
    for s in range(slide_count, 0, -1):
        size = choice[s][i]
        segments[s - 1] = "\n".join(units[i - size:i])
        i -= size
    return {"segments": segments, "unitCount": unit_count, "mode": "one-per-slide" if sparse else "content-aligned"}


def attach_script_notes(slides: Sequence[Mapping[str, Any]], script_body: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fill empty ``speakerNotes`` of enabled slides from the script.

    Slides that already carry teacher-written notes are never overwritten, and
    nothing is changed unless every enabled slide is still empty (otherwise the
    teacher has already started narrating by hand).
    """
    result = [dict(slide) for slide in slides]
    enabled = [index for index, slide in enumerate(result) if slide.get("enabled", True) is not False]
    if not enabled or any(str(result[index].get("speakerNotes") or "").strip() for index in enabled):
        return result, {"applied": False, "reason": "notes-present" if enabled else "no-slides"}
    outcome = align_script_to_slides(script_body, [result[index] for index in enabled])
    if not outcome["unitCount"]:
        return result, {"applied": False, "reason": "empty-script"}
    truncated = 0
    for position, index in enumerate(enabled):
        text = outcome["segments"][position]
        if len(text) > NOTES_LIMIT:
            text, truncated = text[:NOTES_LIMIT], truncated + 1
        result[index]["speakerNotes"] = text
    return result, {
        "applied": True, "mode": outcome["mode"], "unitCount": outcome["unitCount"],
        "slideCount": len(enabled), "emptySlides": sum(1 for text in outcome["segments"] if not text), "truncated": truncated,
    }


def latest_approved_script(scripts: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """``scripts`` is newest-first (see media_script_repository.list_scripts)."""
    for script in scripts:
        if script.get("status") == "approved" and str(script.get("body") or "").strip():
            return script
    return None
