"""Edit-mode upload: result hosts exist, files are not listed twice, errors name their step."""
import re
import unittest
from pathlib import Path

SRC = (Path(__file__).resolve().parents[1] / "static" / "course-wizard-681.js").read_text(encoding="utf-8")
HOST = 'id="cw681-material-insights"'


class EditModeUploadTests(unittest.TestCase):
    def test_every_result_block_with_background_jobs_has_insight_hosts(self):
        blocks = [line for line in SRC.splitlines() if "state.resultHtml=" in line and 'id="cw681-background-jobs"' in line]
        self.assertGreaterEqual(len(blocks), 3)  # create, retry, add-to-course
        for line in blocks:
            self.assertIn(HOST, line)
            self.assertIn('id="cw681-atlas-import"', line)

    def test_add_files_to_course_does_not_append_the_same_file_twice(self):
        body = SRC[SRC.index("async function addFilesToCourse"):]
        body = body[: body.index("async function createAndPublish")]
        self.assertNotIn("state.files=[...state.files,...picked]", body)
        self.assertIn("state.files.includes(file)", body)

    def test_insights_still_shown_when_finishing_steps_fail(self):
        self.assertIn("finishStep", SRC)
        catch = SRC[SRC.index("let finishStep"):]
        catch = catch[: catch.index("syncCompletionControls();")]
        self.assertIn("hydrateCompletedMaterialInsights(completedMaterialIds)", catch.split("}catch(error){", 1)[1])

    def test_legacy_doc_hint_is_rendered(self):
        self.assertIn("${review}${docHint}${fix}", SRC)



class PersistentAtlasEntryTests(unittest.TestCase):
    def test_docx_material_rows_have_a_permanent_atlas_button(self):
        self.assertIn("atlasImportButton(m)", SRC)
        self.assertIn('data-cw-mat-action="atlas"', SRC)
        self.assertIn("action==='atlas'", SRC)

    def test_atlas_host_is_created_on_demand_next_to_course_materials(self):
        body = SRC[SRC.index("async function openCourseAtlasImport"):]
        body = body[: body.index("async function watchQueuedJobs")]
        self.assertIn("data-cw681-course-materials", body)
        self.assertIn('insertAdjacentHTML(\'afterend\'', body)


if __name__ == "__main__":
    unittest.main()


class OpenEditNeverTrapsTheUserTests(unittest.TestCase):
    def _open_edit_body(self):
        start = SRC.index("const plan=await api('/api/courses/'+encodeURIComponent(courseId)+'/plan');")
        return SRC[start - 200: start + 4200]

    def test_material_link_check_does_not_block_opening_an_existing_course(self):
        body = self._open_edit_body()
        self.assertIn("try{await verifyCreatedCourseMaterials();}catch", body)

    def test_failed_open_resets_the_half_open_course(self):
        body = self._open_edit_body()
        self.assertIn("clearWizardState();render();", body)
