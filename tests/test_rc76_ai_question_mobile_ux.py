from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def source(path): return (ROOT/path).read_text(encoding="utf-8")
def test_ai_stage2_uses_direct_workspace_switch_with_timeout():
    s=source("static/teacher-content-studio-71.js")
    block=s[s.index("async function mountAiPanel"):s.index("async function chooseExamForQuestion")]
    assert "openAdminWorkspace" not in block
    assert "window.switchAdminWorkspace('assessment', true)" in block
    assert "題庫載入逾時" in block and "考卷同步逾時" in block
    assert "1 選考卷 ✓" in block and "3 審核匯入" in block
def test_question_rows_use_one_primary_action_and_overflow_menu():
    s=source("static/admin-question-editor-ui.js")
    assert "✏️ 編輯</button><details" in s
    assert "✏️ 快速編輯" not in s
    assert "qselection-actions-" in s
    assert "actions?.classList.toggle('hidden',selected.length===0)" in s
    assert "if(cb) cb.checked=true" not in s
def test_bulk_toolbar_is_selection_driven_and_duplicate_sticky_save_is_gone():
    s=source("static/admin-question-bank.js")
    assert "勾選題目後顯示批次工具" in s
    assert "qselection-actions-${c.id}" in s
    assert "📝 全選編輯" not in s
    assert "qsticky-save-" not in s
