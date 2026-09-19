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
        entrypoint=ROOT.joinpath('pgy_app.py').read_text(encoding='utf-8')
        factory=ROOT.joinpath('teacher_app','factory.py').read_text(encoding='utf-8')
        self.assertIn('from teacher_app import create_app',entrypoint)
        self.assertIn('register_smart_learning',factory)
    def test_smart_slide_uses_native_pdf_and_pptx_text(self):
        adapter=ROOT.joinpath('smart_learning_67.py').read_text(encoding='utf-8')
        content=ROOT.joinpath('teacher_app','learning','content.py').read_text(encoding='utf-8')
        routes=ROOT.joinpath('teacher_app','learning','routes.py').read_text(encoding='utf-8')
        self.assertIn('zipfile.ZipFile',content)
        self.assertIn('page.get_text',content)
        self.assertIn('from teacher_app.learning.content import (',adapter)
        self.assertNotIn('def extract_slide_text(',adapter)
        self.assertIn('from teacher_app.learning.routes import (',adapter)
        self.assertIn('material-search/<material_id>/index',routes)

    def test_learning_sql_is_owned_by_canonical_repository(self):
        adapter=ROOT.joinpath('smart_learning_67.py').read_text(encoding='utf-8')
        routes=ROOT.joinpath('teacher_app','learning','routes.py').read_text(encoding='utf-8')
        repository=ROOT.joinpath('teacher_app','learning','repository.py').read_text(encoding='utf-8')
        for sql in ('SELECT * FROM learning_progress','INSERT INTO learning_progress','UPDATE learning_progress','FROM material_text_index','INTO material_text_index','FROM material_search_status','INTO material_search_status'):
            self.assertNotIn(sql,adapter)
            self.assertNotIn(sql,routes)
        for table in ('learning_progress','material_text_index','material_search_status'):
            self.assertIn(table,repository)
        for call in ('repository.get_progress','repository.upsert_progress','repository.update_media_progress','repository.search_material','repository.replace_text_index','repository.get_index_status','repository.write_terminal_status'):
            self.assertIn(call,routes)
        self.assertNotIn('app.test_client()',adapter)
        self.assertNotIn('app.test_client()',routes)
    def test_docx_import_uses_one_canonical_preview_parser(self):
        smart=ROOT.joinpath('smart_learning_67.py').read_text(encoding='utf-8')
        atlas=ROOT.joinpath('teacher_app','atlas','routes.py').read_text(encoding='utf-8')
        importer=ROOT.joinpath('teacher_app','atlas','importer.py').read_text(encoding='utf-8')
        self.assertIn('def preview_docx_atlas',importer)
        self.assertIn('atlas_importer.preview_import',atlas)
        self.assertNotIn('from smart_learning_67 import preview_docx_atlas',atlas)
        self.assertNotIn('/api/docx-atlas-preview/',smart)
        self.assertIn('SmartArt',importer)
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
        schema=ROOT.joinpath('teacher_app','maintenance','migrations.py').read_text(encoding='utf-8')
        self.assertIn('0067-smart-learning-content',schema)
        self.assertIn('CREATE TABLE IF NOT EXISTS learning_progress',schema)

    def test_phase2_index_contract_has_safe_terminal_hook_and_admin_ui(self):
        smart=ROOT.joinpath('smart_learning_67.py').read_text(encoding='utf-8')
        routes=ROOT.joinpath('teacher_app','learning','routes.py').read_text(encoding='utf-8')
        worker=ROOT.joinpath('teacher_app','worker','routes.py').read_text(encoding='utf-8')
        admin=ROOT.joinpath('static/admin-materials.js').read_text(encoding='utf-8')
        self.assertIn('def auto_index_material', smart)
        self.assertIn('"no_text"', routes)
        self.assertIn('auto_index_material(app', worker)
        self.assertIn('worker_repository.transition_owned_material_job(', worker)
        self.assertIn('"status": "completed"', worker)
        self.assertIn('rebuildMaterialIndex', admin)
        self.assertIn('hydrateMaterialIndexStatus', admin)

    def test_phase2_docx_wizard_ui_contract(self):
        wizard=ROOT.joinpath('static/atlas-docx-wizard-70.js').read_text(encoding='utf-8')
        self.assertIn('openAtlasDocxWizard', wizard)
        self.assertIn('/preview', wizard)
        self.assertIn('/confirm', wizard)
        self.assertIn('去識別化', wizard)

if __name__=='__main__': unittest.main()
