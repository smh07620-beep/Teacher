from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN_CSS = ROOT / "static" / "admin.css"


def test_teacher_content_studio_stays_above_mobile_admin_modal():
    css = ADMIN_CSS.read_text(encoding="utf-8")
    assert '#admin-modal {' in css
    assert 'z-index: 200 !important;' in css
    assert '#teacher-content-studio-71 {' in css
    assert 'z-index: 260 !important;' in css


def test_launcher_is_scoped_to_authoring_workspaces_only():
    css = ADMIN_CSS.read_text(encoding="utf-8")
    selector = (
        '#admin-modal:not([data-workspace="course-materials"])'
        ':not([data-workspace="assessment"]) '
        '#teacher-content-studio-launcher-71'
    )
    assert selector in css
    assert 'display: none !important;' in css
