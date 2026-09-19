import subprocess
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class ManagementSurfaceSimplification78Tests(unittest.TestCase):
    def src(self,path): return ROOT.joinpath(path).read_text(encoding='utf-8')

    def test_exam_flow_billboard_is_retired(self):
        html=self.src('static/system.html')
        self.assertNotIn('V5.7.0 EXAM FLOW',html)
        self.assertNotIn('id="admin-quiz-guide"',html)
        self.assertIn('data-teacher78-canonical-create-executor',html)
        self.assertIn('清單只負責搜尋與開啟考卷',html)

    def test_exam_list_is_compact_searchable_and_paged(self):
        bank=self.src('static/admin-question-bank.js')
        for marker in ('quizListView78','visible:20','teacher78FilterQuizCategories','teacher78SetQuizStatus','teacher78LoadMoreQuizCategories','data-quiz-overflow-78','開啟考卷'):
            self.assertIn(marker,bank)
        self.assertNotIn('🧠 題庫／AI（<span id="qcount-',bank)
        self.assertIn('window.openTeacherContentExam?.',bank)

    def test_material_entry_is_one_container(self):
        studio=self.src('static/teacher-content-studio-71.js')
        self.assertIn("card('materials-manager'",studio)
        self.assertIn('mountMaterialManagerInStudio',studio)
        self.assertIn('data-material-hub-host-78',studio)
        self.assertNotIn("card('material','📄','上傳教材'",studio)
        self.assertNotIn("card('video-material'",studio)

    def test_identity_meta_has_one_profile_owner(self):
        html=self.src('static/system.html'); core=self.src('static/system-core.js'); profile=self.src('static/training-command-center-71.js')
        self.assertIn('載入身分…',html)
        self.assertIn("dataset.profileHydrated!=='1'",core)
        self.assertIn("meta.dataset.profileHydrated = '1'",profile)
        self.assertNotIn("set('v573-system-user-id',empId?",core)

    def test_modified_browser_js_syntax(self):
        for asset in ('admin-question-bank.js','teacher-content-studio-71.js','system-core.js','training-command-center-71.js'):
            result=subprocess.run(['node','--check',str(ROOT/'static'/asset)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr or result.stdout)

if __name__=='__main__': unittest.main()
