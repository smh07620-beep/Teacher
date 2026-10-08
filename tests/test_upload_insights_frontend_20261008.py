import unittest
from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[1] / "static" / "course-wizard-681.js").read_text(encoding="utf-8")


class UploadInsightsFrontendTests(unittest.TestCase):
    def test_teacher_no_longer_picks_a_type_before_upload(self):
        self.assertNotIn("✨ 自動判定</option>", SOURCE)
        self.assertNotIn("aria-label=\"教材類型\"", SOURCE)
        self.assertIn("materialType:'auto'", SOURCE)

    def test_results_show_as_each_job_completes_from_stored_analysis(self):
        self.assertIn("hydratedJobIds", SOURCE)
        self.assertIn("storageMeta?.uploadAnalysis", SOURCE)
        self.assertIn("內含 ${imageCount} 張圖", SOURCE)

    def test_single_question_and_correction_path(self):
        for marker in ("待確認", "courseWizard681ConfirmType", "courseWizard681ChangeType", "更正類型"):
            self.assertIn(marker, SOURCE)


if __name__ == "__main__":
    unittest.main()
