"""Regression contracts for the teacher workspace interaction recovery."""
from pathlib import Path
from unittest.mock import patch

from flask import Flask, g, jsonify

from teacher_app.assessments.routes import register_assessment_routes


ROOT = Path(__file__).resolve().parents[1]


def test_internal_area_and_batch_entry_are_not_blocked_by_recovery_click_handler():
    authoring = (ROOT / "static" / "teacher-authoring-source-fix-1017.js").read_text(encoding="utf-8")
    batch = (ROOT / "static" / "teacher-assignment-experience-1014.js").read_text(encoding="utf-8")
    assert "typeof window.TeacherWorkspace1014?.openMedia === 'function') return" in authoring
    assert "teacher-batch-assignment-dialog-1014" in batch
    assert "wizard-area" in batch
    assert "hub?._adminCourseMaterialRefresh" in batch
    assert "wizardAreaRefreshQueued" in (ROOT / "static" / "admin-question-bank.js").read_text(encoding="utf-8")


def test_exam_settings_return_uses_the_canonical_assessment_router():
    html = (ROOT / "static" / "system.html").read_text(encoding="utf-8")
    router = (ROOT / "static" / "admin-workspace.js").read_text(encoding="utf-8")
    assert "switchAdminWorkspace('assessment',true)" in html
    assert "name === 'exams'" in router


def test_subtitle_picker_owns_its_selected_material():
    subtitle = (ROOT / "static" / "teacher-media-subtitle-1014.js").read_text(encoding="utf-8")
    authoring = (ROOT / "static" / "teacher-authoring-source-fix-1017.js").read_text(encoding="utf-8")
    assert "teacher-subtitle-material-1017" in subtitle
    assert "TeacherMediaSubtitle1014?.selectMaterial" in authoring
    assert "subtitleBridge1017" not in authoring


def test_delete_route_checks_persisted_exam_scope_before_cascade():
    routes = (ROOT / "teacher_app" / "assessments" / "routes.py").read_text(encoding="utf-8")
    assert "scope_filter.scoped_groups" in routes
    assert '"question.manage"' in routes
    assert '"cascadeQuestions": True' in routes


def _delete_app():
    app = Flask(__name__)
    app.secret_key = "scope-delete-test"

    @app.before_request
    def bind_actor():
        g.teacher_user = {"username": "teacher1", "role": "clinical_teacher", "roles": ["clinical_teacher"]}

    register_assessment_routes(app)
    return app


def test_teacher_exam_detail_reads_draft_by_persisted_id_and_scope():
    app = _delete_app()
    category = {"id": "quiz-draft", "group": "grpBio", "area": "internal", "title": "Draft", "active": False}
    with app.test_client() as client, \
         patch("teacher_app.assessments.routes.rbac_legacy_adapter.legacy_admin_guard", return_value=None), \
         patch("teacher_app.assessments.routes.repository.get_category_full", return_value=category), \
         patch("teacher_app.assessments.routes.scope_filter.scoped_groups", return_value=(g, None)) as scoped:
        response = client.get("/api/quiz-categories/quiz-draft")
    assert response.status_code == 200
    assert response.get_json()["id"] == "quiz-draft"
    assert response.get_json()["active"] is False
    assert scoped.call_args.args[2] == {"grpBio"}


def test_teacher_exam_detail_fails_closed_outside_persisted_group_scope():
    app = _delete_app()
    category = {"id": "quiz-other", "group": "grpHema", "area": "internal", "title": "Other", "active": False}
    with app.test_client() as client, \
         patch("teacher_app.assessments.routes.rbac_legacy_adapter.legacy_admin_guard", return_value=None), \
         patch("teacher_app.assessments.routes.repository.get_category_full", return_value=category), \
         patch("teacher_app.assessments.routes.scope_filter.scoped_groups", side_effect=lambda *_: (None, (jsonify({"error": "此資源不在你的授權範圍。"}), 403))):
        response = client.get("/api/quiz-categories/quiz-other")
    assert response.status_code == 403


def test_scoped_teacher_can_delete_exam_in_own_group_only():
    app = _delete_app()
    category = {"id": "quiz-own", "group": "grpBio", "area": "internal", "title": "Own"}
    with app.test_client() as client, \
         patch("teacher_app.assessments.routes.rbac_legacy_adapter.legacy_admin_guard", return_value=None), \
         patch("teacher_app.assessments.routes.repository.get_category_full", return_value=category), \
         patch("teacher_app.assessments.routes.scope_filter.scoped_groups", return_value=(g, None)) as scoped, \
         patch("teacher_app.assessments.routes.service.delete_category", return_value={"ok": True}) as delete, \
         patch("teacher_app.assessments.routes.audit.record_event"):
        response = client.delete("/api/quiz-categories/quiz-own")
    assert response.status_code == 200
    delete.assert_called_once()
    assert scoped.call_args.args[2] == {"grpBio"}


def test_scoped_teacher_cannot_delete_exam_outside_group():
    app = _delete_app()
    category = {"id": "quiz-other", "group": "grpHema", "area": "internal", "title": "Other"}
    with app.test_client() as client, \
         patch("teacher_app.assessments.routes.rbac_legacy_adapter.legacy_admin_guard", return_value=None), \
         patch("teacher_app.assessments.routes.repository.get_category_full", return_value=category), \
         patch("teacher_app.assessments.routes.scope_filter.scoped_groups", side_effect=lambda *_: (None, (jsonify({"error": "此資源不在你的授權範圍。"}), 403))), \
         patch("teacher_app.assessments.routes.service.delete_category") as delete:
        response = client.delete("/api/quiz-categories/quiz-other")
    assert response.status_code == 403
    delete.assert_not_called()
