"""The first uploaded script source can be kept as the course's main material (not purged)."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT.joinpath("static", "teacher-media-script-1014.js").read_text(encoding="utf-8")
STUDIO = ROOT.joinpath("static", "teacher-ai-media-studio-1018.js").read_text(encoding="utf-8")
WIZARD = ROOT.joinpath("static", "course-wizard-681.js").read_text(encoding="utf-8")


class KeepSourceTests(unittest.TestCase):
    def test_checkbox_is_shown_only_inside_the_course_wizard(self):
        self.assertIn('id="teacher-script-keep-source-1033" type="checkbox" checked', SCRIPT)
        self.assertIn("keepRow.hidden = !window.TeacherCourseAuthoringContext?.active", SCRIPT)

    def test_only_a_finished_flow_keeps_the_source(self):
        self.assertIn("options.finished && keepSourceRequested()", SCRIPT)
        self.assertIn("cleanupPrivateSources?.({finished: true})", STUDIO)
        # abandoning / discarding still removes every private source
        discard = SCRIPT[SCRIPT.index("async function discardAll()"):][:200]
        self.assertIn("return cleanupPrivateSources();", discard)

    def test_wizard_links_the_kept_source_as_a_course_material(self):
        self.assertIn("teacher-ai-source-kept", SCRIPT)
        self.assertIn("window.addEventListener('teacher-ai-source-kept'", WIZARD)
        self.assertIn("item.asSource?{courseId:state.course.id,active:true,desc:''}", WIZARD)


if __name__ == "__main__":
    unittest.main()
