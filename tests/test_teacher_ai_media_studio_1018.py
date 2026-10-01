from pathlib import Path

from teacher_app.frontend.assets import ASSET_MANIFEST


ROOT = Path(__file__).resolve().parents[1]


def test_media_studio_is_loaded_after_the_existing_media_controls():
    body = ASSET_MANIFEST["system"]["body"]
    assert "/teacher-ai-media-studio-1018.js" in body
    assert body.index("/teacher-ai-video-1015.js") < body.index("/teacher-ai-media-studio-1018.js")
    assert body.index("/teacher-authoring-source-fix-1017.js") < body.index("/teacher-ai-media-studio-1018.js")


def test_media_studio_keeps_one_source_and_accessible_single_mode_tabs():
    source = ROOT.joinpath("static", "teacher-ai-media-studio-1018.js").read_text(encoding="utf-8")
    for token in (
        "teacher-ai-media-studio-1018",
        "teacher-media-source-1018",
        "teacher-media-next-step-1018",
        "role', 'tablist",
        "aria-selected",
        "aria-controls",
        "ArrowLeft",
        "ArrowRight",
        "panel.hidden = !selected",
        "TeacherMediaSubtitle1014?.selectMaterial",
    ):
        assert token in source


def test_media_shell_has_no_duplicate_source_placeholder_and_keeps_a_small_return_action():
    source = ROOT.joinpath("static", "teacher-workspace-1014.js").read_text(encoding="utf-8")
    assert "準備媒體來源" in source  # Removes stale markup produced by older workspace hydrations.
    assert "data-teacher-media-source-placeholder-1014" in source
    assert "teacher-media-shell-actions-1014" in source
    assert "回教材與課程" in source
    assert "回教材與課程選擇" not in source


def test_media_studio_reuses_existing_generate_review_publish_lanes_without_internal_id_entry():
    source = ROOT.joinpath("static", "teacher-ai-media-studio-1018.js").read_text(encoding="utf-8")
    audio = ROOT.joinpath("static", "teacher-media-audio-1014.js").read_text(encoding="utf-8")
    video = ROOT.joinpath("static", "teacher-ai-video-1015.js").read_text(encoding="utf-8")
    assert "/api/ai-presentations?materialId=" in source
    assert "replaceVideoIdInput" in source
    assert "/api/media-audio/preview" in audio
    assert "▶ 試聽" in audio
    assert "/api/media-audio/generate" in audio
    assert "/api/ai-videos/generate" in video
    assert "/approve" in video and "/publish" in video
    assert "data.model" not in audio
    assert "data.provider" not in audio
