"""Loaded-browser contracts complement the route-level workflow tests."""
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class FeatureExposureUi681Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assessment = ROOT.joinpath("static", "assessment-681.js").read_text(encoding="utf-8")
        cls.wizard = ROOT.joinpath("static", "course-wizard-681.js").read_text(encoding="utf-8")
        cls.external = ROOT.joinpath("static", "external-material-681.js").read_text(encoding="utf-8")
        cls.media = ROOT.joinpath("static", "smart-learning-67.js").read_text(encoding="utf-8")

    def test_five_tabs_call_real_assessment_apis(self):
        for name in ("考卷", "題庫", "AI 出題", "出題藍圖", "題目分析"):
            self.assertIn(name, self.assessment)
        for path in ("/api/question-bank/drafts", "/api/question-bank/", "/api/exam-blueprints",
                     "/api/questions/", "/api/ai-questions/generate"):
            self.assertIn(path, self.assessment)

    def test_editor_carries_source_and_review_source_payload(self):
        for field in ("learningObjective", "sourceMaterialId", "reviewSource", "timeStart", "pageEnd"):
            self.assertIn(field, self.assessment)
        self.assertIn("previewSource", self.assessment)

    def test_stepper_preserves_files_and_supports_all_exam_choices(self):
        self.assertIn("state.files", self.wizard)
        for choice in ("稍後建立", "從題庫選", "AI 草稿", "Blueprint"):
            self.assertIn(choice, self.wizard)
        self.assertIn("MaterialUploadClient.enqueue", self.wizard)
        self.assertNotIn("/api/slides/upload", self.wizard)

    def test_external_creation_has_no_storage_or_worker_caller(self):
        self.assertIn("/api/materials/external", self.external)
        for forbidden in ("/api/material-jobs", "/api/r2", "/api/mega", "<iframe"):
            self.assertNotIn(forbidden, self.external.lower())

    def test_canonical_media_tracks_coverage_and_review_seek(self):
        for marker in ("watchedBuckets", "completionThreshold:.9", "teacher681SeekReviewSource",
                       "youtube-nocookie.com", "/external-media"):
            self.assertIn(marker, self.media)


if __name__ == "__main__":
    unittest.main()
