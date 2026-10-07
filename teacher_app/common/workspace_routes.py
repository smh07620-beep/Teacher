"""Back-office workspace routes: one table for URLs, areas and aliases.

The back office has eleven internal workspace keys that belong to four
human-facing product areas (docs/PRODUCT_INFORMATION_ARCHITECTURE_20261001.md).
Server code that needs a link into a workspace builds it here instead of
hand-writing ``/system?...workspace=...`` strings.

The same table lives in ``static/workspace-routes-1007.js``; a test keeps the two
identical.  This is presentation routing only: authorization is enforced on the
server by the RBAC helpers, never by a link.
"""
from __future__ import annotations

from typing import Mapping
from urllib.parse import quote

AREAS = {
    "learning": "我的學習",
    "teaching": "教學",
    "assessment": "評量",
    "system": "系統管理",
}

# key -> product area
WORKSPACE_AREAS = {
    "course-materials": "teaching",
    "word": "teaching",
    "assessment": "assessment",
    "teacher": "assessment",
    "results": "assessment",
    "compliance": "assessment",
    "people": "system",
    "system": "system",
    "maintenance": "system",
    "audit": "system",
    "worker": "system",
}

ALIASES = {
    "courses": "course-materials",
    "materials": "course-materials",
    "questions": "assessment",
    "exams": "assessment",
    "scoring": "teacher",
    "pgy": "teacher",
}

DEFAULT_WORKSPACE = "course-materials"
PAGE_PATH = "/system"


def normalize(name: str) -> str:
    key = str(name or "").strip()
    return ALIASES.get(key, key)


def area_of(name: str) -> str:
    key = normalize(name)
    try:
        return WORKSPACE_AREAS[key]
    except KeyError:
        raise ValueError(f"Unknown workspace: {name!r}") from None


def is_system(name: str) -> bool:
    return normalize(name) in WORKSPACE_AREAS and area_of(name) == "system"


def workspace_url(
    name: str,
    *,
    area: str = "",
    group: str = "",
    persona: str = "",
    source: str = "",
    params: Mapping[str, str] | None = None,
) -> str:
    """Build ``/system?...`` for a workspace, in the same query order as the JS side."""
    area_of(name)  # reject unknown workspaces loudly
    pairs = [
        ("area", area),
        ("group", group),
        ("admin", "1"),
        ("workspace", name),
        ("persona", persona or ("system" if is_system(name) else "")),
        ("from", source),
    ]
    pairs.extend((params or {}).items())
    query = "&".join(
        f"{quote(str(key), safe='')}={quote(str(value), safe='')}"
        for key, value in pairs
        if value not in (None, "")
    )
    return f"{PAGE_PATH}?{query}"
