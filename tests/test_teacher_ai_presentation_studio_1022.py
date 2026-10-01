"""Contracts for the consolidated AI PowerPoint authoring studio."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TeacherAiPresentationStudio1022Tests(unittest.TestCase):
    def test_authoring_sources_use_direct_upload_and_remain_private_by_default(self):
        source = (ROOT / "static" / "teacher-ai-material-1014.js").read_text(encoding="utf-8")
        for marker in ("MaterialUploadClient.enqueue", "multiple", ".xlsx", "active:false", "data-remove-authoring-source", "teacher-ai-material-request-publication"):
            self.assertIn(marker, source)


    def test_studio_carries_internal_draft_state_without_rendering_id_fields(self):
        source = (ROOT / "static" / "teacher-ai-presentation-1016.js").read_text(encoding="utf-8")
        for marker in ("teacher-ai-material-draft-selected", "draftId:selectedDraft.id", "selectedDraft.status !== 'approved'", "teacher-ai-material-published", "publicationMaterialId"):
            self.assertIn(marker, source)
        self.assertNotIn("aidraft-", source)
        self.assertNotIn("正式教材 ID", source)


    def test_presentation_route_keeps_rbac_scope_and_quality_gate(self):
        source = (ROOT / "teacher_app" / "materials" / "ai_presentation_routes.py").read_text(encoding="utf-8")
        for marker in ('denied = _capability(user, "presentation.create"', "denied = _scope(owner", 'draft.get("draftType") != "slides"', 'draft.get("status") != "approved"', 'manifest.get("status") == "error"', 'body.get("acknowledgeWarnings") is not True', "repository.create_publication("):
            self.assertIn(marker, source)


    def test_course_manage_button_reconciles_at_card_scope(self):
        source = (ROOT / "static" / "teacher-interface-convergence-1014.js").read_text(encoding="utf-8")
        for marker in ("details.querySelectorAll('[data-teacher-manage-course-1014]')", "manages.forEach(node => node.remove())", "manage.parentElement !== actionHost"):
            self.assertIn(marker, source)
