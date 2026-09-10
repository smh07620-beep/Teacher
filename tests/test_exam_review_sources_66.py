import unittest
from pathlib import Path

from teacher_app.exams import grading


ROOT = Path(__file__).parents[1]


class ExamReviewSources66Tests(
    unittest.TestCase
):
    def sample(self):
        return {
            "id": "q1",
            "question":
                "QC 異常時應先做什麼？",
            "questionType":
                "choice",
            "options":
                ["A", "B", "C", "D"],
            "correct": 2,
            "explanation":
                "教師內部解析，不可傳給 learner。",
            "answerConfig": {
                "correctIndices": [2],
                "acceptedAnswers": [
                    "secret"
                ],
                "reviewSource": {
                    "materialId":
                        "mat-qc",
                    "materialTitle":
                        "QC 教育訓練",
                    "anchorType":
                        "page",
                    "page": 12,
                    "section":
                        "異常處理流程",
                    "reviewHint":
                        "重新確認校正與 QC 的先後順序。",
                },
            },
        }

    def test_pre_submit_hides_review_source_and_all_answer_secrets(self):
        safe = grading.sanitize_question(
            self.sample()
        )

        for key in (
            "correct",
            "explanation",
            "reviewSource",
        ):
            self.assertNotIn(
                key,
                safe,
            )

        config = safe.get(
            "answerConfig",
            {},
        )

        for key in (
            "reviewSource",
            "correctIndices",
            "acceptedAnswers",
        ):
            self.assertNotIn(
                key,
                config,
            )

    def test_post_submit_exposes_only_safe_review_source(self):
        reviewed = (
            grading.review_question(
                self.sample()
            )
        )

        self.assertNotIn(
            "correct",
            reviewed,
        )

        self.assertNotIn(
            "explanation",
            reviewed,
        )

        source = reviewed[
            "reviewSource"
        ]

        self.assertEqual(
            source[
                "materialId"
            ],
            "mat-qc",
        )

        self.assertEqual(
            source[
                "anchorType"
            ],
            "page",
        )

        self.assertEqual(
            source[
                "page"
            ],
            12,
        )

        self.assertNotIn(
            "correctIndices",
            reviewed.get(
                "answerConfig",
                {},
            ),
        )

    def test_review_source_supports_page_time_region_and_section(self):
        page = grading.normalize_review_source(
            {
                "materialId": "m1",
                "page": "8",
            }
        )

        self.assertEqual(
            page["anchorType"],
            "page",
        )

        self.assertEqual(
            page["page"],
            8,
        )

        time = grading.normalize_review_source(
            {
                "materialId": "v1",
                "anchorType":
                    "time",
                "timeSeconds":
                    "155",
            }
        )

        self.assertEqual(
            time[
                "timeSeconds"
            ],
            155.0,
        )

        region = grading.normalize_review_source(
            {
                "materialId": "img1",
                "regionHint":
                    "影像左下方",
            }
        )

        self.assertEqual(
            region["anchorType"],
            "region",
        )

        section = grading.normalize_review_source(
            {
                "materialId": "m2",
                "section":
                    "QC 異常流程",
            }
        )

        self.assertEqual(
            section["anchorType"],
            "section",
        )

    def test_submit_service_uses_safe_review_projection(self):
        source = ROOT.joinpath(
            "teacher_app/exams/service.py"
        ).read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "grading.sanitize_question(q)",
            source,
        )

        self.assertIn(
            "grading.review_question(question)",
            source,
        )


if __name__ == "__main__":
    unittest.main()
