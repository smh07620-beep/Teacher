import unittest
from pathlib import Path

ROOT=Path(__file__).parents[1]

class SmartLearning67Tests(unittest.TestCase):
    def test_reader_tracks_page_without_open_equals_complete(self):
        source=ROOT.joinpath('static/smart-learning-67.js').read_text(encoding='utf-8')
        self.assertIn('learning-progress',source)
        self.assertIn('p>=t',source)
        self.assertIn('save({page:p}',source)
    def test_adapter_keeps_legacy_app(self):
        self.assertIn('register_smart_learning',ROOT.joinpath('pgy_app.py').read_text(encoding='utf-8'))
    def test_smart_slide_uses_native_pdf_and_pptx_text(self):
        source=ROOT.joinpath('smart_learning_67.py').read_text(encoding='utf-8')
        self.assertIn('zipfile.ZipFile',source)
        self.assertIn('page.get_text',source)
        self.assertIn('material-search/<material_id>/index',source)
    def test_docx_import_is_preview_first(self):
        source=ROOT.joinpath('smart_learning_67.py').read_text(encoding='utf-8')
        self.assertIn('preview_docx_atlas',source)
        self.assertIn('publishRequired',source)
        self.assertIn('SmartArt',source)
    def test_media_pipeline_is_not_an_http_thread_transcode(self):
        source=ROOT.joinpath('media_processing_67.py').read_text(encoding='utf-8')
        self.assertIn('subprocess.run([path',source)
        self.assertNotIn('shell=True',source)
        self.assertIn('material_jobs',source)
        self.assertNotIn('def worker_once',source)
    def test_media_progress_is_batched_and_not_autoplay_hack(self):
        source=ROOT.joinpath('static/smart-learning-67.js').read_text(encoding='utf-8')
        self.assertIn('15000',source)
        self.assertIn("['pause','ended']",source)
        self.assertNotIn('.play()',source)
    def test_review_source_20_keeps_legacy_time_seconds(self):
        source=ROOT.joinpath('teacher_app/exams/grading.py').read_text(encoding='utf-8')
        self.assertIn('timeSeconds',source); self.assertIn('timeStart',source); self.assertIn('"region"',source)
    def test_0067_is_additive_and_required(self):
        schema=ROOT.joinpath('schema_migrations.py').read_text(encoding='utf-8')
        self.assertIn('0067-smart-learning-content',schema)
        self.assertIn('CREATE TABLE IF NOT EXISTS learning_progress',schema)

    def test_phase2_index_contract_has_safe_terminal_hook_and_admin_ui(self):
        smart=ROOT.joinpath('smart_learning_67.py').read_text(encoding='utf-8')
        worker=ROOT.joinpath('free_worker_67.py').read_text(encoding='utf-8')
        admin=ROOT.joinpath('static/admin-materials.js').read_text(encoding='utf-8')
        self.assertIn('def auto_index_material', smart)
        self.assertIn('"no_text"', smart)
        self.assertIn('auto_index_material(base', worker)
        self.assertIn('status="completed"', worker)
        self.assertIn('rebuildMaterialIndex', admin)
        self.assertIn('hydrateMaterialIndexStatus', admin)

    def test_phase2_docx_wizard_ui_contract(self):
        wizard=ROOT.joinpath('static/atlas-docx-wizard-70.js').read_text(encoding='utf-8')
        self.assertIn('openAtlasDocxWizard', wizard)
        self.assertIn('/preview', wizard)
        self.assertIn('/confirm', wizard)
        self.assertIn('去識別化', wizard)

if __name__=='__main__': unittest.main()
