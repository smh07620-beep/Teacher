from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WIZARD = (ROOT / "static" / "course-wizard-681.js").read_text(encoding="utf-8")
STUDIO = (ROOT / "static" / "teacher-content-studio-71.js").read_text(encoding="utf-8")
AUDIO = (ROOT / "static" / "teacher-media-audio-1014.js").read_text(encoding="utf-8")
VIDEO = (ROOT / "static" / "teacher-ai-video-1015.js").read_text(encoding="utf-8")
CSP = (ROOT / "static" / "system-csp-actions.js").read_text(encoding="utf-8")


class CourseWizardEditModeTests(unittest.TestCase):
    def test_wizard_exposes_edit_and_upload_actions(self):
        self.assertIn("window.courseWizard681EditCourse=editCourse", WIZARD)
        self.assertIn("window.courseWizard681AddFiles=addFilesToCourse", WIZARD)
        self.assertIn("'courseWizard681EditCourse'", CSP)
        self.assertIn("'courseWizard681AddFiles'", CSP)

    def test_edit_mode_loads_existing_course_and_keeps_published_state(self):
        self.assertIn("'/api/courses/'+encodeURIComponent(courseId)+'/plan'", WIZARD)
        self.assertIn("state.course=course;state.created=true;state.editing=true;", WIZARD)
        self.assertIn("await verifyCreatedCourseMaterials();", WIZARD)
        self.assertIn("完成並返回課程", WIZARD)

    def test_edit_mode_never_overwrites_an_unfinished_new_course(self):
        self.assertIn("state.created&&!state.editing", WIZARD)
        self.assertIn("請先完成或發布它，再編輯其他課程", WIZARD)

    def test_reset_paths_clear_edit_flag(self):
        self.assertGreaterEqual(WIZARD.count("state.editing=false;"), 3)

    def test_new_course_never_inherits_the_edited_course(self):
        self.assertIn("window.courseWizard681StartNew=startNewCourse", WIZARD)
        self.assertIn("function startNewCourse()", WIZARD)
        # create entry points and closing the studio all reset edit mode
        self.assertGreaterEqual(STUDIO.count("courseWizard681StartNew"), 3)

    def test_studio_opens_wizard_in_edit_mode(self):
        self.assertIn("window.openTeacherCourseEditWorkspace=openCourseEditWorkspace", STUDIO)
        self.assertIn("window.courseWizard681EditCourse?.(courseId,step)", STUDIO)

    def test_narration_and_video_return_to_wizard(self):
        self.assertIn("teacher-ai-narration-published", AUDIO)
        self.assertIn("teacher-ai-video-published", VIDEO)
        self.assertIn("addEventListener('teacher-ai-narration-published'", WIZARD)
        self.assertIn("addEventListener('teacher-ai-video-published'", WIZARD)
        self.assertIn("'AI 教學影片',true", WIZARD)


if __name__ == "__main__":
    unittest.main()
