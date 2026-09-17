from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class ContentContainerConvergence77Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.studio=ROOT.joinpath('static/teacher-content-studio-71.js').read_text(encoding='utf-8')
        cls.ai=ROOT.joinpath('static/admin-ai-questions.js').read_text(encoding='utf-8')

    def test_studio_outer_surface_only_exposes_exam_management(self):
        self.assertIn("'考卷管理'",self.studio)
        self.assertNotIn("card('question'",self.studio)
        self.assertNotIn("card('image-question'",self.studio)
        self.assertNotIn("card('video-question'",self.studio)
        self.assertNotIn("card('ai-question'",self.studio)

    def test_exam_is_question_container(self):
        for token in ('renderExamManager','renderExamContainer','data-exam-action="question"','data-exam-action="image"','data-exam-action="video"','data-exam-action="ai"','data-exam-action="questions"','data-exam-action="settings"'):
            self.assertIn(token,self.studio)
        self.assertIn("confirmQuestionPreset('choice',catId)",self.studio)
        self.assertIn("mountAiPanel(catId)",self.studio)

    def test_exam_creation_keeps_canonical_mutation_owner(self):
        self.assertIn('adminCreateQuizCategory',self.studio)
        self.assertNotIn("fetch('/api/quiz-categories'",self.studio)

    def test_course_wizard_is_mounted_inside_studio(self):
        self.assertIn('mountCourseWizardInStudio',self.studio)
        self.assertIn('data-course-wizard-host-77',self.studio)
        self.assertIn('restoreCourseWizard',self.studio)
        self.assertNotIn("closeStudio();\n      await window.openAdminWorkspace?.('course-materials');\n      window.teacher75OpenCourseWizard?.();",self.studio)

    def test_ai_uses_current_exam_and_has_bounded_prepare_flow(self):
        self.assertNotIn('chooseExamForAi',self.studio)
        self.assertIn('const deadline=Date.now()+6000',self.studio)
        for text in ('正在切換考卷工作區','正在讀取考卷','正在開啟題庫','正在掛載 AI 出題工作室','↻ 重新嘗試'):
            self.assertIn(text,self.studio)

    def test_ai_primary_surface_is_purpose_plus_count(self):
        self.assertIn('data-ai-primary-count-77',self.studio)
        self.assertIn('data-ai-material-details-77',self.studio)
        self.assertIn('data-ai-advanced-77',self.studio)

    def test_ai_auto_selects_up_to_four_linked_materials(self):
        self.assertIn("mats.filter(m=>m.category===id)",self.ai)
        self.assertIn("auto.slice(0,4)",self.ai)
        self.assertIn("kind(m)[0]!=='video'",self.ai)

if __name__=='__main__': unittest.main()
