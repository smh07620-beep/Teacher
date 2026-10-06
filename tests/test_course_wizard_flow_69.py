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
        for marker in ('課程設定', '教材＋AI', '評量／考卷', '確認發布'):
            self.assertIn(marker, self.source)
        self.assertNotIn("const steps=['課程設定','教材','評量與 AI','確認發布']", self.source)
        self.assertIn("state.files", self.source)
        self.assertIn("state.existing", self.source)
        self.assertIn(">上一步</button>", self.source)

    def test_course_setup_can_plan_assignment_due_date_and_optional_ai_before_publish(self):
        for marker in (
            "/api/learning-assignments/audience-options",
            "發布後立即建立學習指派",
            "課程性質",
            "完成期限",
            "createWizardAssignment",
            "/api/learning-assignments",
            "AI_PLAN_META",
            "不需要 AI 製作",
            "AI PowerPoint",
            "講稿與配音",
            "AI 教學影片",
            "openTeacherCourseMediaAuthoring",
            "courseWizard681OpenAiAuthoring",
            "teacher-ai-presentation-published",
            "attachAiProducts",
        ):
            self.assertIn(marker, self.source)

    def test_exam_modes_match_guided_course_authoring_contract(self):
        for marker in (
            "later:{label:'稍後建立'",
            "bank:{label:'自己出題'",
            "ai:{label:'AI 協助出題'",
            "blueprint:{label:'Blueprint（進階）'",
            "ensureAssessmentDraft",
            "openTeacherCourseAssessmentAuthoring",
            "courseWizard681OpenAssessmentAuthoring",
        ):
            self.assertIn(marker, self.source)
        self.assertNotIn("bank:{label:'從題庫選'", self.source)
        self.assertNotIn("ai:{label:'AI 草稿'", self.source)
        self.assertIn("進階：Blueprint／題型配額", self.source)

    def test_created_course_links_existing_and_queues_new_materials(self):
        self.assertIn("courseId:course.id", self.source)
        self.assertIn("for(const id of state.existing)", self.source)
        # Uploading is now centralized in uploadEntries so the same safe
        # queueing path can be reused for retries.
        self.assertIn("const entries=files.map((file,index)=>({file,index}));", self.source)
        self.assertIn("await uploadEntries(entries", self.source)
        self.assertIn("form.append('courseId',courseId)", self.source)
        self.assertIn("form.append('category',categoryId)", self.source)
        self.assertIn("MaterialUploadClient.enqueue", self.source)
        self.assertNotIn("/api/slides/upload", self.source)

    def test_upload_failures_are_visible_instead_of_console_only(self):
        self.assertIn('const errors=[],jobs=[]', self.source)
        self.assertIn("errors.push({index:item.index,fileName:file.name,reason})", self.source)
        self.assertIn('以下教材尚未進入 Worker', self.source)
        self.assertIn('教材上傳未完整完成', self.source)
        self.assertIn('error?.message', self.source)

    def test_course_checkpoint_does_not_create_exam_until_assessment_step(self):
        create = self.source[self.source.index('async function create()'):self.source.index('async function ensureCourseDraft()')]
        self.assertIn("api('/api/course-bundles'", create)
        self.assertIn("examMode:'later',examTitle:''", create)
        self.assertNotIn('examMode:state.examMode', create)
        self.assertIn("api('/api/quiz-categories'", self.source)
        self.assertIn("courseId:state.course.id", self.source)
        self.assertIn('"draft"', self.bundle)
        self.assertIn('"active": False', self.bundle)
        self.assertNotIn('/publish', create)

    def test_first_step_waits_for_rbac_before_claiming_assignment_denial(self):
        self.assertIn("assignPermission:null", self.source)
        self.assertIn("TeacherRBAC681Ready", self.source)
        self.assertIn("正在確認你的學習指派權限", self.source)
        self.assertIn("resolveAssignmentPermission", self.source)

    def test_publish_is_only_step_four_and_does_not_launch_ai_after_publish(self):
        self.assertIn("courseWizard681CreateAndPublish", self.source)
        self.assertIn("確認並正式發布", self.source)
        publish = self.source[self.source.index('async function publishAndOpenCourseWorkspace()'):self.source.index('async function openCourseWorkspace()')]
        self.assertNotIn("TeacherAIMediaStudio1018?.showMode", publish)
        self.assertNotIn("openMedia", publish)


if __name__ == '__main__':
    unittest.main()
