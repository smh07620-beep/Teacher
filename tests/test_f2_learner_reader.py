import unittest
from pathlib import Path

from teacher_app.learning import content


ROOT = Path(__file__).parents[1]


class F2LearnerReaderTests(unittest.TestCase):
    def test_document_completion_requires_coverage_and_last_page(self):
        jumped = content.document_completion(10, [10], 0.9)
        self.assertFalse(jumped["completed"])
        self.assertEqual(jumped["progress"], 10.0)

        coverage_without_end = content.document_completion(10, range(1, 10), 0.9)
        self.assertFalse(coverage_without_end["completed"])
        self.assertEqual(coverage_without_end["progress"], 90.0)

        completed = content.document_completion(10, range(1, 11), 0.9)
        self.assertTrue(completed["completed"])
        self.assertEqual(completed["progress"], 100.0)

    def test_trackable_reader_sends_total_pages_not_client_completion(self):
        source = ROOT.joinpath("static", "smart-learning-67.js").read_text(encoding="utf-8")
        self.assertIn("totalPages:t", source)
        self.assertIn("smartLearning67:progress", source)
        self.assertNotIn("save({page:p},Math.round(p/t*100),p>=t)", source)

    def test_f2_layer_removes_manual_completion_for_trackable_materials(self):
        source = ROOT.joinpath("static", "learner-reading-progress-f2.js").read_text(encoding="utf-8")
        self.assertIn("window.markMaterialComplete", source)
        self.assertIn("autoTracked(material)", source)
        self.assertIn("/api/learning-progress", source)
        self.assertIn("需要重新閱讀", source)

    def test_f2_asset_is_loaded_in_system(self):
        source = ROOT.joinpath("teacher_app", "frontend", "assets.py").read_text(encoding="utf-8")
        self.assertIn('"/learner-reading-progress-f2.js"', source)


if __name__ == "__main__":
    unittest.main()
