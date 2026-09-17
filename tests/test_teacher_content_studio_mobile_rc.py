from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "static" / "teacher-content-studio-71.js"
ADMIN_CSS = ROOT / "static" / "admin.css"


def test_teacher_content_studio_stays_above_mobile_admin_modal():
    js = STUDIO.read_text(encoding="utf-8")
    css = ADMIN_CSS.read_text(encoding="utf-8")
    assert "z-[260]" in js
    assert "z-index: 200 !important" in css


def test_launcher_is_scoped_to_content_authoring_workspaces():
    js = STUDIO.read_text(encoding="utf-8")
    assert "course-materials" in js
    assert "assessment" in js
    assert "syncLauncherVisibility" in js
    assert "attributeFilter:['data-workspace','data-section']" in js
