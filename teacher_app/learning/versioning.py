"""Pure helpers for version-aware material completion and retraining."""
from __future__ import annotations

from typing import Any, Iterable, Mapping


def _version(value: Any, default: int = 1) -> int:
    try:
        return max(1, int(value or default))
    except (TypeError, ValueError):
        return default


def current_version(material: Mapping[str, Any] | None) -> int:
    material = material or {}
    return _version(material.get("currentVersion", material.get("current_version", 1)))


def required_completion_version(material: Mapping[str, Any] | None) -> int:
    material = material or {}
    required = _version(
        material.get(
            "requiredCompletionVersion",
            material.get("required_completion_version", 1),
        )
    )
    return min(required, current_version(material))


def completion_is_current(
    material: Mapping[str, Any] | None,
    completed_version: Any,
) -> bool:
    return _version(completed_version) >= required_completion_version(material)


def classify_completion(
    material: Mapping[str, Any] | None,
    completed_version: Any,
) -> dict[str, Any]:
    completed = _version(completed_version)
    required = required_completion_version(material)
    current = current_version(material)
    valid = completed >= required
    return {
        "completedVersion": completed,
        "requiredCompletionVersion": required,
        "currentVersion": current,
        "completionCurrent": valid,
        "retrainingRequired": not valid,
    }


def valid_completed_material_ids(
    materials: Iterable[Mapping[str, Any]],
    progress_rows: Iterable[Mapping[str, Any] | Any],
) -> tuple[set[str], set[str]]:
    material_map = {
        str(item.get("id") or ""): item
        for item in materials
        if str(item.get("id") or "")
    }
    valid: set[str] = set()
    stale: set[str] = set()
    for raw in progress_rows:
        row = dict(raw)
        material_id = str(row.get("material_id") or row.get("materialId") or "")
        material = material_map.get(material_id)
        if not material:
            continue
        completed_version = row.get("completed_version", row.get("completedVersion", 1))
        if completion_is_current(material, completed_version):
            valid.add(material_id)
        else:
            stale.add(material_id)
    return valid, stale


__all__ = [
    "classify_completion",
    "completion_is_current",
    "current_version",
    "required_completion_version",
    "valid_completed_material_ids",
]
