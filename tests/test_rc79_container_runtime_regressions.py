from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]

class RC79ContainerRuntimeRegressions(unittest.TestCase):
    def src(self,path): return (ROOT/path).read_text(encoding="utf-8")

    def test_web_image_installs_office_components_for_supported_sync_formats(self):
        dockerfile=self.src("Dockerfile")
        classification=self.src("teacher_app/materials/classification.py")
        self.assertIn("FROM python:3.12-slim-bookworm",dockerfile)
        self.assertIn("megacmd-Debian_12_amd64.deb",dockerfile)
        for package in ("libreoffice-writer","libreoffice-calc","libreoffice-impress"):
            self.assertIn(package,dockerfile)
        for extension in ('.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp'):
            self.assertIn(extension,classification)

    def test_web_image_retains_system_tools_for_live_canonical_web_callers(self):
        dockerfile=self.src("Dockerfile")
        run_web=self.src("run_web.sh")
        sync_runtime=self.src("teacher_app/materials/sync_runtime.py")
        storage_runtime=self.src("teacher_app/storage/worker_runtime.py")
        web_storage=self.src("teacher_app/storage/web_runtime.py")
        ai_runtime=self.src("teacher_app/assessments/ai_runtime.py")

        for package in ("ffmpeg", "qpdf", "fonts-noto-cjk"):
            self.assertIn(package,dockerfile)
        self.assertIn("megacmd-Debian_12_amd64.deb",dockerfile)
        self.assertIn('CMD ["bash", "run_web.sh"]',dockerfile)
        self.assertIn("pgy_app:app",run_web)
        self.assertNotIn("material_worker.py",run_web.splitlines()[-1])

        # The Web synchronous upload composer intentionally reuses the canonical
        # storage/conversion adapter, so qpdf and soffice are still Web runtime
        # dependencies rather than worker-image-only packages.
        self.assertIn("WorkerMaterialStorageAdapter()",sync_runtime)
        self.assertIn("self.storage._office_to_pdf",sync_runtime)
        self.assertIn("self.storage._save_optimized_pdf",sync_runtime)
        self.assertIn('shutil.which("qpdf")',storage_runtime)
        self.assertIn('self.soffice = os.environ.get("SOFFICE_PATH", "soffice")',storage_runtime)

        # Canonical Web reads still execute MEGAcmd, and video AI generation is
        # still in-process on Web and shells out to ffmpeg/ffprobe.
        self.assertIn('["mega-get", str(file_id), str(tempdir)]',web_storage)
        self.assertIn('["ffmpeg", "-y", "-i", str(video)',ai_runtime)
        self.assertIn('["ffprobe", "-v", "error"',ai_runtime)

    def test_home_outer_surface_is_flat(self):
        css=self.src("static/portal.css")
        self.assertIn(".v56-shell{width:100%;margin:0;background:transparent;border:0;border-radius:0;box-shadow:none",css)
        self.assertNotIn(".v56-shell{width:min(1380px,calc(100% - 36px));margin:18px auto 0",css)

    def test_quiz_list_recollapses_runtime_panels(self):
        bank=self.src("static/admin-question-bank.js")
        self.assertIn("function collapseQuizPanels78",bank)
        self.assertIn("setTimeout(()=>collapseQuizPanels78(box),0)",bank)

    def test_exam_container_cards_have_single_delegated_handler(self):
        studio=self.src("static/teacher-content-studio-71.js")
        self.assertIn("window.teacherContentStudioExamAction=(action,catId)=>dispatchExamAction(action,catId)",studio)
        self.assertIn("dispatchExamAction(examAction.dataset.examAction, examAction.dataset.examId)",studio)
        self.assertIn("const handler=examActionHandlers.get(String(action))",studio)
        self.assertNotIn('onclick="event.stopPropagation();window.teacherContentStudioExamAction',studio)
        for action in ("question","image","video","ai","questions","settings"):
            self.assertIn(f'data-exam-action="{action}"',studio)

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
