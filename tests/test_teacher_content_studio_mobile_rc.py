from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN_CSS = ROOT / "static" / "admin.css"


def test_teacher_content_task_view_is_inline_not_a_second_mobile_modal():
    css = ADMIN_CSS.read_text(encoding="utf-8")
    assert '#admin-modal {' in css
    assert 'z-index: 200 !important;' in css
    assert '#teacher-content-studio-71 {' in css
    assert 'max-width: 1500px;' in css
    assert '.teacher-content-workspace-card {' in css
    assert 'z-index: 260 !important;' not in css


def test_old_cross_workspace_launcher_is_retired():
    css = ADMIN_CSS.read_text(encoding="utf-8")
    assert '#teacher-content-studio-launcher-71' not in css
    assert 'body[data-teacher-content-studio-open="1"] #admin-workspace-content > .admin-section-panel' in css
