"""Linear authoring flow: correct wizard return, navigation lock, discard drafts, no leftover private sources."""
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask, g

from teacher_app.materials.ai_material_routes import register_ai_material_routes

ROOT = Path(__file__).resolve().parents[1]


def _read(name):
    return ROOT.joinpath("static", name).read_text(encoding="utf-8")


class AuthoringFlowFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.studio = _read("teacher-ai-media-studio-1018.js")
        cls.script = _read("teacher-media-script-1014.js")
        cls.audio = _read("teacher-media-audio-1014.js")
        cls.material = _read("teacher-ai-material-1014.js")
        cls.content = _read("teacher-content-studio-71.js")

    def test_finish_returns_to_the_course_wizard_step_not_course_overview(self):
        self.assertIn("window.TeacherCourseAuthoringContext", self.studio)
        self.assertLess(
            self.studio.index("returnTeacherCourseAuthoringStep"),
            self.studio.index("TeacherWorkspace1014?.openCourse"),
        )
        self.assertIn("finishAndReturn", self.audio)

    def test_authoring_screen_locks_other_workspaces_and_offers_abandon(self):
        self.assertIn("addWorkspaceGuard", self.content)
        self.assertIn("data-course-authoring-abandon", self.content)
        self.assertIn("resetFlowState", self.content)

    def test_script_import_and_generate_are_one_action_with_discard_and_revise_at_bottom(self):
        self.assertNotIn('id="teacher-script-source-upload-1030"', self.script)
        self.assertNotIn('id="teacher-script-paste-add-1030"', self.script)
        for marker in ("importAndGenerate", "✨ 匯入並產生講稿", "teacher-script-discard-1032",
                       "teacher-script-regenerate-1032", "method:'DELETE'", "goToAudioStep"):
            self.assertIn(marker, self.script)
        # narration no longer gets the pinned top bar
        self.assertIn("mode === 'narration'", self.studio)

    def test_temporary_private_sources_are_cleaned_after_finish_or_abandon(self):
        self.assertIn("cleanupPrivateSources", self.script)
        self.assertIn("cleanupAuthoringSources", self.material)
        self.assertIn("cleanupPrivateSources", self.studio)
        self.assertIn("cleanupAuthoringSources", self.studio)
        self.assertIn("cleanupAuthoringSources", self.content)

    def test_presentation_has_single_import_generate_action_and_discard(self):
        for marker in ("importAndGenerateDraft", "✨ 匯入並產生 PowerPoint 大綱",
                       "teacher-ai-material-discard-1032", "/api/ai-material-drafts/"):
            self.assertIn(marker, self.material)


class AiMaterialDraftDiscardRouteTests(unittest.TestCase):
    def _app(self, group="grpBio"):
        app = Flask(__name__)
        app.secret_key = "test"

        @app.before_request
        def bind_user():
            g.teacher_user = {"username": "t1", "role": "clinical_teacher", "roles": ["clinical_teacher"], "preferredGroup": group}

        register_ai_material_routes(app)
        return app

    def test_unpublished_draft_can_be_discarded(self):
        draft = {"id": "d1", "group": "grpBio", "draftType": "slides", "title": "大綱", "status": "draft", "publicationMaterialId": ""}
        with self._app().test_client() as client, \
             patch("teacher_app.materials.ai_material_routes.media_script_repository.get_script", return_value=draft), \
             patch("teacher_app.materials.ai_material_routes.media_script_repository.delete_script", return_value=True) as delete, \
             patch("teacher_app.materials.ai_material_routes.audit.record_event"):
            response = client.delete("/api/ai-material-drafts/d1")
        self.assertEqual(response.status_code, 200)
        delete.assert_called_once_with("d1")

    def test_published_draft_and_other_group_are_refused(self):
        published = {"id": "d2", "group": "grpBio", "draftType": "slides", "publicationMaterialId": "mat-9"}
        other = {"id": "d3", "group": "grpBB", "draftType": "slides", "publicationMaterialId": ""}
        with self._app().test_client() as client, \
             patch("teacher_app.materials.ai_material_routes.media_script_repository.get_script", return_value=published), \
             patch("teacher_app.materials.ai_material_routes.media_script_repository.delete_script") as delete:
            self.assertEqual(client.delete("/api/ai-material-drafts/d2").status_code, 409)
        with self._app().test_client() as client, \
             patch("teacher_app.materials.ai_material_routes.media_script_repository.get_script", return_value=other), \
             patch("teacher_app.materials.ai_material_routes.media_script_repository.delete_script") as delete:
            self.assertEqual(client.delete("/api/ai-material-drafts/d3").status_code, 403)
            delete.assert_not_called()


if __name__ == "__main__":
    unittest.main()
