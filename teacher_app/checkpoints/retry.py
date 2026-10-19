"""Second attempt for a checkpoint answered wrong the first time.

The first answer stays the learning record (slide_checkpoint_answers).  The
optional second attempt lives in the learner's own reading progress
(``learning_progress.position["checkpointRetry"]``) so no schema change is
needed; the progress endpoint carries the key forward on every save.
"""
from __future__ import annotations

import datetime as dt
import json
from typing import Any

from teacher_app.learning import repository as learning_repository

KEY = "checkpointRetry"


def _position(row: dict) -> dict:
    try:
        value = json.loads((row or {}).get("position") or "{}")
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def retries_for(username: str, material_id: str) -> dict[str, dict]:
    try:
        row = learning_repository.get_progress(str(material_id), str(username))
    except Exception:
        return {}
    value = _position(row).get(KEY) or {}
    return {str(k): v for k, v in value.items() if isinstance(v, dict)} if isinstance(value, dict) else {}


def record(username: str, material_id: str, checkpoint_id: str, chosen: int, correct: bool) -> None:
    row = learning_repository.get_progress(str(material_id), str(username)) or {}
    position = _position(row)
    retries = position.get(KEY) if isinstance(position.get(KEY), dict) else {}
    if str(checkpoint_id) in retries:
        return  # only one retry; a repeat call keeps the first retry
    retries = dict(retries)
    retries[str(checkpoint_id)] = {"chosenIndex": int(chosen), "isCorrect": bool(correct)}
    position[KEY] = retries
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    learning_repository.upsert_progress(
        str(material_id),
        str(username),
        position=position,
        progress=float(row.get("progress") or 0),
        completed=False,  # the upsert keeps an existing completion (OR) and its date
        last_viewed_at=now,
        completed_at=str(row.get("completed_at") or ""),
    )


def carry_forward(prior: Any, position: Any) -> None:
    """Keep the retry record when the reader saves a freshly built position."""
    if not isinstance(prior, dict) or not isinstance(position, dict):
        return
    value = prior.get(KEY)
    if isinstance(value, dict) and value and KEY not in position:
        position[KEY] = value
