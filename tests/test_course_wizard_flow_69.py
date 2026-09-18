import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class CourseWizardFlow69Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROOT.joinpath('static', 'course-wizard-681.js').read_text(encoding='utf-8')
        cls.bundle = ROOT.joinpath('teacher_app', 'courses', 'bundle.py').read_text(encoding='utf-8')

    def test_wizard_uses_session_rbac_not_admin_key_header(self):
        self.assertIn("credentials:'same-origin'", self.source)
        self.assertIn("response.status===401", self.source)
        self.assertIn("response.status===403", self.source)
        self.assertIn("登入已逾時，請重新登入", self.source)
        self.assertNotIn('getAdminKey', self.source)
        self.assertNotIn('X-Admin-Key', self.source)

    def test_wizard_preserves_four_clear_steps(self):
        for marker in ('基本資料', '教材', '題目與考卷', '確認建立'):
            self.assertIn(marker, self.source)
        self.assertIn("state.files", self.source)
        self.assertIn("state.existing", self.source)

    def test_exam_modes_have_explicit_next_action(self):
        for marker in ("later:{label:'稍後建立'", "bank:{label:'從題庫選'", "ai:{label:'AI 草稿'", "blueprint:{label:'Blueprint'"):
            self.assertIn(marker, self.source)
        self.assertIn("courseWizard681Continue", self.source)
        self.assertIn("switchAdminWorkspace('assessment',true)", self.source)
        self.assertIn('前往題庫與考卷', self.source)

    def test_created_course_links_existing_and_queues_new_materials(self):
        self.assertIn("courseId:course.id", self.source)
        self.assertIn("for(const id of state.existing)", self.source)
        self.assertIn("for(let index=0;index<files.length;index++)", self.source)
        self.assertIn("form.append('courseId',course.id)", self.source)
        self.assertIn("form.append('category',state.categoryId)", self.source)
        self.assertIn("MaterialUploadClient.enqueue", self.source)
        self.assertNotIn("/api/slides/upload", self.source)

    def test_exam_is_created_as_skeleton_without_auto_publish(self):
        create = self.source[self.source.index('async function create()'):self.source.index('async function continueToAssessment()')]
        self.assertIn("api('/api/course-bundles'", create)
        self.assertIn('examMode:state.examMode', create)
        self.assertIn('"draft"', self.bundle)
        self.assertIn('False if kind == "postgres" else 0', self.bundle)
        self.assertNotIn('/publish', create)
        self.assertNotIn('publishExam', create)
        self.assertNotIn('publishQuiz', create)


if __name__ == '__main__':
    unittest.main()
