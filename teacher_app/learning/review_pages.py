"""Pages a learner must re-read after a failed exam (stored in learning_progress.position)."""
from __future__ import annotations

import datetime as dt
import json
from typing import Any, Iterable, Mapping

from teacher_app.learning import repository


def pages_by_material(review_questions: Iterable[Mapping[str, Any]]) -> dict[str, list[int]]:
    """Wrong questions with a page-anchored reviewSource -> {materialId: [pages]}."""
    result: dict[str, set[int]] = {}
    for item in review_questions or []:
        if not isinstance(item, Mapping) or item.get("isCorrect") is not False:
            continue
        source = item.get("reviewSource") or {}
        material_id = str(source.get("materialId") or "")
        try:
            page = int(source.get("page") or 0)
        except (TypeError, ValueError):
            page = 0
        if material_id and page > 0:
            result.setdefault(material_id, set()).add(page)
    return {key: sorted(value) for key, value in result.items()}


def plant(username: str, by_material: Mapping[str, list[int]]) -> None:
    """Record the pages to re-read; the exam gate then waits for those pages only."""
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    for material_id, pages in by_material.items():
        row = repository.get_progress(material_id, username)
        if not row:
            continue  # never opened: the normal completion rule already applies
        try:
            position = json.loads(row.get("position") or "{}")
        except Exception:
            position = {}
        if not isinstance(position, dict):
            position = {}
        merged = sorted({int(p) for p in position.get("reviewPages") or [] if isinstance(p, int)} | set(pages))
        position["reviewPages"] = merged
        position["reviewDwell"] = {}
        repository.upsert_progress(
            material_id,
            username,
            position=position,
            progress=float(row.get("progress") or 0),
            completed=bool(row.get("completed")),
            last_viewed_at=now,
            completed_at=str(row.get("completed_at") or ""),
        )


def advance(position: dict, page: int, delta: Mapping[str, float], required_by_page: Mapping[str, int], rules_v2: bool) -> None:
    """Credit the current visit toward pending review pages and clear the ones that are done."""
    pending = [p for p in position.get("reviewPages") or [] if isinstance(p, int)]
    if not pending:
        position["reviewPages"] = []
        return
    if not rules_v2:
        position["reviewPages"] = [p for p in pending if p != page]
        return
    dwell = dict(position.get("reviewDwell") or {})
    for key, seconds in delta.items():
        if int(key) in pending:
            dwell[key] = round(float(dwell.get(key, 0)) + float(seconds), 1)
    position["reviewDwell"] = dwell
    position["reviewPages"] = [
        p for p in pending if float(dwell.get(str(p), 0)) < float(required_by_page.get(str(p), 5))
    ]
