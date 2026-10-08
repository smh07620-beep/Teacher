"""Contracts for the consolidated AI PowerPoint authoring studio."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TeacherAiPresentationStudio1022Tests(unittest.TestCase):
    def test_authoring_sources_use_direct_upload_and_remain_private_by_default(self):
        source = (ROOT / "static" / "teacher-ai-material-1014.js").read_text(encoding="utf-8")
        for marker in ("MaterialUploadClient.enqueue", "multiple", ".xlsx", ".pdf", ".docx", ".pptx", "teacher-ai-material-paste-1014", "addPastedSource", "authoringOnly", "data-remove-authoring-source", "teacher-ai-material-request-publication"):
            self.assertIn(marker, source)


    def test_studio_carries_internal_draft_state_without_rendering_id_fields(self):
        source = (ROOT / "static" / "teacher-ai-presentation-1016.js").read_text(encoding="utf-8")
        for marker in ("teacher-ai-material-draft-selected", "draftId:selectedDraft.id", "selectedDraft.status !== 'approved'", "teacher-ai-material-published", "publicationMaterialId"):
            self.assertIn(marker, source)
        self.assertNotIn("aidraft-", source)
        self.assertNotIn("正式教材 ID", source)


    def test_powerpoint_picker_has_one_option_owner_and_visible_label_dedupe(self):
        material = (ROOT / "static" / "teacher-ai-material-1014.js").read_text(encoding="utf-8")
        controls = (ROOT / "static" / "teacher-ai-media-controls-1023.js").read_text(encoding="utf-8")
        self.assertIn("teacher-ai-material-options-rendered-1014", material)
        self.assertIn("item.title || item.filename || item.id", material)
        self.assertNotIn("String(item.courseId || '').trim(),", material)
        self.assertNotIn("paintSelect($('teacher-ai-material-source-1014')", controls)
        self.assertNotIn("authoring.add(new Option", controls)
        self.assertIn("option.selected = true", controls)
        self.assertIn("materialOptionsGeneration", material)
        self.assertIn("select.replaceChildren(...options)", material)
        self.assertNotIn("select.appendChild(option)", material)

    def test_presentation_publish_defaults_to_current_revision_and_collapses_history(self):
        source = (ROOT / "static" / "teacher-ai-presentation-1016.js").read_text(encoding="utf-8")
        for marker in (
            "目前工作中的投影片",
            "正式發布目前版本",
            "teacher-ai-presentation-history-1016",
            "歷史版本／改用其他投影片",
            "只列目前 presentation family",
            "currentPresentationId",
            "data-use-presentation",
            "type=\"hidden\"",
            "不再要求從以前的 PowerPoint 或舊教材清單重新挑選",
        ):
            self.assertIn(marker, source)
        self.assertNotIn("<select id=\"teacher-ai-presentation-publication-material-1016\"", source)

    def test_presentation_route_keeps_rbac_scope_and_quality_gate(self):
        source = (ROOT / "teacher_app" / "materials" / "ai_presentation_routes.py").read_text(encoding="utf-8")
        for marker in ('denied = _capability(user, "presentation.create"', "denied = _scope(owner", 'draft.get("draftType") != "slides"', 'draft.get("status") != "approved"', 'manifest.get("status") == "error"', 'body.get("acknowledgeWarnings") is not True', "repository.create_publication("):
            self.assertIn(marker, source)


    def test_course_manage_button_reconciles_at_card_scope(self):
        source = (ROOT / "static" / "teacher-interface-convergence-1014.js").read_text(encoding="utf-8")
        for marker in ("details.querySelectorAll('[data-teacher-course-actions-1014]')", "groups.forEach(node => node.remove())", "group.parentElement !== actionHost"):
            self.assertIn(marker, source)

    def test_media_loading_has_one_presentation_owner_and_bounded_requests(self):
        studio = (ROOT / "static" / "teacher-ai-media-studio-1018.js").read_text(encoding="utf-8")
        controls = (ROOT / "static" / "teacher-ai-media-controls-1023.js").read_text(encoding="utf-8")
        video = (ROOT / "static" / "teacher-ai-video-1015.js").read_text(encoding="utf-8")
        self.assertIn("presentationMaterialId", studio)
        self.assertIn("refreshPresentationChoices:", studio)
        self.assertIn("void refreshVideoPresentations(materialId, {force});", controls)
        self.assertNotIn("TeacherAIMediaStudio1018?.refreshPresentationChoices", controls)
        self.assertIn("sourceRefreshPromise", controls)
        self.assertIn("scheduleEnhance();", controls)
        self.assertNotIn("[0, 400, 1200, 3000, 7000, 12000]", controls)
        self.assertIn("AbortController", studio)
        self.assertIn("AbortController", controls)
        self.assertIn("AbortController", video)
