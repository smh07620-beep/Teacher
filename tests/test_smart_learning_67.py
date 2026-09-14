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

if __name__=='__main__': unittest.main()
