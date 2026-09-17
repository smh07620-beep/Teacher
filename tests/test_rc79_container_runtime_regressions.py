from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]

class RC79ContainerRuntimeRegressions(unittest.TestCase):
    def src(self,path): return (ROOT/path).read_text(encoding="utf-8")

    def test_home_outer_surface_is_flat(self):
        css=self.src("static/portal-v56.css")
        self.assertIn(".v56-shell{width:100%;margin:0;background:transparent;border:0;border-radius:0;box-shadow:none",css)
        self.assertNotIn(".v56-shell{width:min(1380px,calc(100% - 36px));margin:18px auto 0",css)

    def test_quiz_list_recollapses_runtime_panels(self):
        bank=self.src("static/admin-question-bank.js")
        self.assertIn("function collapseQuizPanels78",bank)
        self.assertIn("setTimeout(()=>collapseQuizPanels78(box),0)",bank)

    def test_exam_container_cards_have_explicit_handlers(self):
        studio=self.src("static/teacher-content-studio-71.js")
        self.assertIn("window.teacherContentStudioExamAction=(action,catId)=>runExamAction(action,catId)",studio)
        for action in ("question","image","video","ai","questions","settings"):
            self.assertIn(f"window.teacherContentStudioExamAction?.('{action}'",studio)

    def test_material_container_mounts_before_background_refresh(self):
        studio=self.src("static/teacher-content-studio-71.js")
        self.assertIn("data-material-refresh-status-79",studio)
        self.assertIn("renderAdminCourseMaterialHub?.(false),8000",studio)
        self.assertNotIn("renderAdminCourseMaterialHub?.(true),3500,'整理課程與教材'",studio)

    def test_browser_js_syntax(self):
        for asset in ("teacher-content-studio-71.js","admin-question-bank.js"):
            r=subprocess.run(["node","--check",str(ROOT/"static"/asset)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr or r.stdout)

if __name__=="__main__": unittest.main()
