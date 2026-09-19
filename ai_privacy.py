"""Legacy adapter for canonical AI privacy policy."""
from __future__ import annotations

from teacher_app.common import privacy

MEDIA_EXT = privacy.MEDIA_EXT
deidentify_text = privacy.deidentify_text
_wrap_text_extractor = privacy.wrap_text_extractor
_install_extractor_wrappers = privacy.install_extractor_wrappers
_external_enabled = privacy.external_enabled
_external_media_allowed = privacy.external_media_allowed


def register_ai_privacy(base):
    return privacy.register_ai_privacy(
        base.app,
        material_lookup=base.get_material,
    )


__all__ = ["MEDIA_EXT", "deidentify_text", "register_ai_privacy"]
