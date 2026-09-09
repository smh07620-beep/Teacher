import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class ExamReviewLinksFrontend66Tests(
    unittest.TestCase
):
    def source(self, rel):
        return ROOT.joinpath(
            rel
        ).read_text(
            encoding="utf-8"
        )

    def test_review_frontend_supports_all_material_anchor_types(self):
        source = self.source(
            "static/review-links-66.js"
        )

        for marker in (
            "reviewAnchorType",
            "reviewPage",
            "reviewTimeSeconds",
            "reviewRegionHint",
            "reviewSection",
            "reviewHint",
            "anchorType",
            "timeSeconds",
            "regionHint",
            "goToSlidePage",
            "media.currentTime",
            "loadedmetadata",
            "openAtlas",
            "考後複習",
        ):
            self.assertIn(
                marker,
                source,
            )

    def test_exam_integrity_still_does_not_expect_explanation_or_answer_key(self):
        source = self.source(
            "static/exam-integrity.js"
        )

        self.assertNotIn(
            "correct:q.correct",
            source,
        )

        self.assertNotIn(
            "explanation:q.explanation",
            source,
        )

        self.assertIn(
            "reviewSource:q.reviewSource",
            source,
        )


if __name__ == "__main__":
    unittest.main()
