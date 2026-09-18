"""Canonical cross-resource search aggregation for Atlas and indexed materials."""
from __future__ import annotations

from typing import Any, Mapping

from teacher_app.atlas import repository as atlas_repository
from teacher_app.atlas import service as atlas_service
from teacher_app.common.errors import ApiError
from teacher_app.learning import repository as learning_repository
from teacher_app.materials import repository as material_repository


def search_resources(user: Mapping[str, Any], query: str, *, limit: int = 100) -> list[dict]:
    """Search readable material text and Atlas metadata without owning their SQL."""
    if not atlas_service.can_read(user):
        raise ApiError("ATLAS_FORBIDDEN", "權限不足。", status=403)

    normalized_query = atlas_service.normalise(query)[: atlas_service.MAX_QUERY]
    if not normalized_query:
        return []

    items: list[dict] = []
    for material in material_repository.list_uploaded_materials(False):
        if not atlas_service.material_visible(user, material):
            continue
        material_id = str(material.get("id") or "")
        for row in learning_repository.get_material_text_rows(material_id, limit=100):
            text = str(row.get("text") or "")
            title = str(row.get("title") or "")
            if normalized_query not in atlas_service.normalise(f"{title} {text}"):
                continue
            start = max(0, atlas_service.normalise(text).find(normalized_query) - 80)
            items.append({
                "type": "material",
                "materialId": material_id,
                "title": material.get("title") or material.get("filename"),
                "group": material.get("group") or material.get("groupKey"),
                "page": int(row.get("page_no") or 0),
                "excerpt": text[start:start + 240],
            })

    groups = atlas_service.readable_groups(user)
    for item in atlas_repository.list_items()[:300]:
        group = str(item.get("group") or "")
        if groups is not None and group not in groups:
            continue
        if not item.get("published") and not atlas_service.can_manage(user, group):
            continue
        text = " ".join([
            str(item.get("title") or ""),
            str(item.get("description") or ""),
            " ".join(item.get("tags") or []),
            str(item.get("differentialPoints") or ""),
        ])
        if normalized_query not in atlas_service.normalise(text):
            continue
        items.append({
            "type": "atlas",
            "atlasItemId": item["id"],
            "title": item["title"],
            "group": item["group"],
            "category": item["category"],
            "excerpt": item["description"] or item["differentialPoints"],
            "imageUrl": item["imageUrl"],
        })

    return items[:limit]
