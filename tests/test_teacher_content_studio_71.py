import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class TeacherContentStudio71Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROOT.joinpath('static/teacher-content-studio-71.js').read_text(encoding='utf-8')
        cls.authoring = ROOT.joinpath('static/question-authoring-ux-71.js').read_text(encoding='utf-8')
        cls.matrix = ROOT.joinpath('RC_FEATURE_UI_COVERAGE_MATRIX.md').read_text(encoding='utf-8')

    def test_task_first_content_types_are_visible(self):
        for label in (
            '建立／管理考卷', '一般考題', '圖片判讀題', '影片互動題', 'AI 輔助出題',
            '上傳教材', '上傳影音教材', '外部影音／連結', '顯微鏡／血球圖譜',
        ):
            self.assertIn(label, self.source)
        self.assertIn('TEACHER CONTENT STUDIO', self.source)
        self.assertIn('＋ 建立教學內容', self.source)

    def test_studio_is_permission_gated_and_does_not_invent_authority(self):
        for permission in ('question.manage', 'exam.manage', 'material.manage', 'course.manage'):
            self.assertIn(permission, self.source)
        self.assertNotIn('professional_title', self.source)
        self.assertNotIn('responsibility_tags', self.source)

    def test_studio_routes_to_existing_canonical_ui_owners(self):
        for marker in (
            'openAdminWorkspace', 'renderAdminQuizCategories', 'toggleQuizQuestionsPanel',
            'updateManualQuestionType', 'openExternalMaterialDrawer', 'switchLearningModule',
            'renderFormalAtlas', 'openAtlasCreate',
        ):
            self.assertIn(marker, self.source)
        self.assertIn('/api/quiz-categories?', self.source)
        self.assertNotIn("method:'POST'", self.source)
        self.assertNotIn("method:'PATCH'", self.source)
        self.assertNotIn("method:'DELETE'", self.source)

    def test_question_presets_select_image_and_video_modes(self):
        self.assertIn("preset === 'image'", self.source)
        self.assertIn("setSelectByValueOrText(typeSelect, 'image')", self.source)
        self.assertIn("preset === 'video'", self.source)
        self.assertIn("String(o.value).startsWith('video_')", self.source)

    def test_authoring_overlay_composes_fresh_studio_asset(self):
        self.assertIn('/teacher-content-studio-71.js?v=7115', self.authoring)
        self.assertIn('presentation-only companion', self.authoring)

    def test_release_matrix_records_studio(self):
        self.assertIn('Teacher content authoring studio (7.1)', self.matrix)
        self.assertIn('static/teacher-content-studio-71.js', self.matrix)

    def test_browser_javascript_syntax(self):
        completed = subprocess.run(
            ['node', '--check', str(ROOT / 'static' / 'teacher-content-studio-71.js')],
            check=False, capture_output=True, text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)


if __name__ == '__main__':
    unittest.main()
