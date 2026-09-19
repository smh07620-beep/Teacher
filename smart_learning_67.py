"""Legacy Smart Learning import adapter.

Runtime HTTP and persistence ownership lives in ``teacher_app.learning``.  This
module keeps historical imports used by the worker and older tests/extensions.
"""
from __future__ import annotations

from teacher_app.learning.content import (
    extract_slide_text,
    media_completion,
    preview_docx_atlas,
    resolved_completion,
)
from teacher_app.learning.routes import (
    auto_index_material as _auto_index_material,
    register_smart_learning as _register_smart_learning,
)


def auto_index_material(base, material_id):
    return _auto_index_material(base, material_id, extractor=lambda path: extract_slide_text(path))


def register_smart_learning(base):
    return _register_smart_learning(base, extractor=lambda path: extract_slide_text(path))


__all__ = [
    "auto_index_material",
    "extract_slide_text",
    "media_completion",
    "preview_docx_atlas",
    "register_smart_learning",
    "resolved_completion",
]
