import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class TeacherContentStudio71Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROOT.joinpath('static/teacher-content-studio-71.js').read_text(encoding='utf-8')
        cls.composer = ROOT.joinpath('static/teacher-content-composer-72.js').read_text(encoding='utf-8')
        cls.convergence = ROOT.joinpath('static/teacher-ux-convergence-72.js').read_text(encoding='utf-8')
        cls.authoring = ROOT.joinpath('static/question-authoring-ux-71.js').read_text(encoding='utf-8')
        cls.external = ROOT.joinpath('static/external-material-681.js').read_text(encoding='utf-8')
        cls.frontend = ROOT.joinpath('pgy_frontend.py').read_text(encoding='utf-8')
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

    def test_phase_two_uses_three_step_guided_flow_and_student_preview(self):
        for marker in ('選擇內容', '編輯內容', '預覽確認', '學生預覽', '建立前檢查', '資料完整，可建立'):
            self.assertIn(marker, self.composer)
        for marker in ('顯微鏡', '血球', '題目圖片預覽', '教師檢查：正確答案／批改方式'):
            self.assertIn(marker, self.composer)
        self.assertIn('decorateQuestionEditor', self.composer)
        self.assertIn('qform-${catId}-${id}', self.composer)
        self.assertIn("v('image')", self.composer)
        self.assertIn("v('media-url')", self.composer)

    def test_convergence_keeps_question_steps_inside_unified_studio(self):
        for marker in ('選擇考卷', '編輯題目', '預覽確認', 'data-teacher72-question-preview', 'data-teacher72-question-submit'):
            self.assertIn(marker, self.convergence)
        self.assertIn("event.stopImmediatePropagation()", self.convergence)
        self.assertIn('prepareCanonicalForm', self.convergence)
        self.assertIn('window.adminAddQuizQuestion?.(state.question.catId)', self.convergence)
        self.assertNotIn("method:'POST'", self.convergence)
        self.assertNotIn("method:'PATCH'", self.convergence)
        self.assertNotIn("method:'DELETE'", self.convergence)

    def test_convergence_reduces_duplicate_authoring_surfaces(self):
        self.assertIn('考卷管理', self.convergence)
        self.assertIn('已建立題目', self.convergence)
        self.assertIn("assessment681Tab('ai')", self.convergence)
        self.assertIn("assessment681Tab('blueprint')", self.convergence)
        self.assertIn("classList.add('hidden')", self.convergence)
        self.assertIn('進階：一次建立整套課程', self.convergence)
        self.assertIn('data-teacher72-course-wizard', self.convergence)

    def test_phase_three_has_readiness_gate_and_post_create_next_actions(self):
        for marker in (
            'questionReadiness', '建立前檢查', '資料完整，可建立',
            '圖片判讀題請上傳題目圖片', '影片題請填入影片網址',
            '繼續出下一題', '回題庫',
        ):
            self.assertIn(marker, self.composer)
        self.assertIn("add.removeAttribute('onclick')", self.composer)
        self.assertIn('window.adminAddQuizQuestion?.(catId)', self.composer)
        self.assertIn('data-composer-submit-question', self.composer)

    def test_phase_three_unifies_material_and_external_completion_feedback(self):
        for marker in (
            '教材已送出處理', '教材部分完成', '查看處理進度', '繼續上傳',
            '外部教材已建立', '外部教材建立失敗', '再新增一筆',
        ):
            self.assertIn(marker, self.composer)
        self.assertIn("result.startsWith('✅')", self.composer)
        self.assertIn("result.startsWith('⚠️')", self.composer)
        self.assertIn("result.startsWith('❌')", self.composer)

    def test_phase_two_material_and_external_flows_delegate_to_canonical_owners(self):
        for marker in (
            'admin-pptx-upload-input', 'adminUploadMaterials', 'admin-material-title',
            'openExternalMaterialCreateDrawer', 'createExternalMaterialFromDrawer',
            'external-material-title', 'external-material-url',
        ):
            self.assertIn(marker, self.composer)
        self.assertIn('確認並開始上傳', self.composer)
        self.assertIn('確認並建立', self.composer)
        self.assertNotIn("method:'POST'", self.composer)
        self.assertNotIn("method:'PATCH'", self.composer)
        self.assertNotIn("method:'DELETE'", self.composer)

    def test_external_direct_create_owner_exposes_stable_aliases(self):
        self.assertIn('window.openExternalMaterialCreateDrawer=window.openExternalMaterialDrawer', self.external)
        self.assertIn('window.createExternalMaterialFromDrawer=window.saveExternalMaterialLink', self.external)

    def test_authoring_overlay_composes_fresh_studio_asset(self):
        self.assertIn('/teacher-content-studio-71.js?v=7115', self.authoring)
        self.assertIn('/teacher-ux-convergence-72.js?v=7202', self.authoring)
        self.assertIn('/teacher-content-composer-72.js?v=7200', self.frontend)
        self.assertLess(
            self.frontend.index('/question-authoring-ux-71.js?v=7130'),
            self.frontend.index('/teacher-content-composer-72.js?v=7200'),
        )

    def test_release_matrix_records_studio(self):
        self.assertIn('Teacher content authoring studio (7.1/7.2)', self.matrix)
        self.assertIn('static/teacher-content-studio-71.js', self.matrix)
        self.assertIn('static/teacher-content-composer-72.js', self.matrix)
        self.assertIn('three-step', self.matrix.lower())
        self.assertIn('繼續出下一題／回題庫', self.matrix)
        self.assertIn('unified success/warning/error outcomes', self.matrix)

    def test_browser_javascript_syntax(self):
        for asset in ('teacher-content-studio-71.js', 'teacher-content-composer-72.js', 'teacher-ux-convergence-72.js'):
            completed = subprocess.run(
                ['node', '--check', str(ROOT / 'static' / asset)],
                check=False, capture_output=True, text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)


if __name__ == '__main__':
    unittest.main()
