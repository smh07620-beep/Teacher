from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUESTION_BANK = ROOT / "static" / "admin-question-bank.js"
QUESTION_ACTIONS = ROOT / "static" / "admin-question-actions.js"
QUESTION_PANEL = ROOT / "static" / "admin-question-panel.js"


def test_question_delete_actions_are_visible_and_explicit():
    source = QUESTION_BANK.read_text(encoding="utf-8")
    assert "window.exposeQuestionDeleteActions" in source
    assert "🗑️ 刪除考卷" in source
    assert "🗑️ 刪除已選題目" in source
    assert "🗑️ 刪除" in source
    assert "MutationObserver" in source


def test_existing_question_delete_contract_keeps_confirmation_and_delete_method():
    source = QUESTION_ACTIONS.read_text(encoding="utf-8")
    assert "window.adminDeleteQuizQuestion" in source
    assert "確定刪除此題目？此操作無法復原。" in source
    assert "method:'DELETE'" in source
    assert "window.adminBulkDeleteQuestions" in source
    assert "確定刪除已選的" in source


def test_existing_exam_delete_contract_keeps_cascade_warning():
    source = QUESTION_PANEL.read_text(encoding="utf-8")
    assert "window.adminDeleteQuizCategory" in source
    assert "頁籤內所有題目也會一併刪除" in source
    assert "/api/quiz-categories/${encodeURIComponent(catId)}" in source
    assert "method:'DELETE'" in source
