import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class LearningFlow66Tests(
    unittest.TestCase
):
    def source(self, rel):
        return ROOT.joinpath(
            rel
        ).read_text(
            encoding="utf-8"
        )

    def test_reader_next_unlocks_immediately_after_completion(self):
        source = self.source(
            "static/teaching.js"
        )

        for marker in (
            "Teacher 6.6 M3 · sequential reader unlock",
            "teacher66SyncReaderNext",
            "teacher66CurrentMaterialDone",
            "完成本份後解鎖",
            "下一份教材 →",
            "requestAnimationFrame",
        ):
            self.assertIn(
                marker,
                source,
            )

        self.assertIn(
            "currentDone",
            source,
        )

        self.assertIn(
            "!currentDone",
            source,
        )

    def test_empty_exam_has_explicit_not_ready_state(self):
        source = self.source(
            "static/teaching.js"
        )

        for marker in (
            "Teacher 6.6 M3 · empty exam guard",
            "teacher66ShowEmptyExam",
            "此考卷尚待題庫建置",
            "尚待題庫建置・目前 0 題",
            "data-empty-exam",
            "data-exam-not-ready",
        ):
            self.assertIn(
                marker,
                source,
            )

        self.assertIn(
            "if (bank === 0)",
            source,
        )

        self.assertIn(
            "loaded.questions.length",
            source,
        )

    def test_m3_teaching_asset_is_cache_busted(self):
        html = self.source(
            "static/system.html"
        )

        self.assertIn(
            "teaching.js?v=6603",
            html,
        )

        # Preserve M2 direct-exam asset.
        self.assertIn(
            "system-exam.js?v=6602",
            html,
        )


if __name__ == "__main__":
    unittest.main()
