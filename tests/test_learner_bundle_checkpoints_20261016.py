import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class LearnerBundleCheckpointsTests(unittest.TestCase):
    def test_bundle_payload_includes_checkpoints_key(self):
        src = (ROOT / "teacher_app/learning/gate.py").read_text(encoding="utf8")
        self.assertIn('"checkpoints": checkpoints', src)
        self.assertIn("learner_items", src)

    def test_learner_items_never_expose_answer_before_answering(self):
        from teacher_app.checkpoints import service
        view = service._learner_view(
            {"id": "cp-1", "page": 1, "question": "q", "options": ["a", "b"], "correctIndex": 1, "explanation": "x"},
            None,
        )
        self.assertNotIn("correctIndex", view)
        self.assertNotIn("explanation", view)

    def test_frontend_prefers_bundled_checkpoints(self):
        loop = (ROOT / "static/learner-study-exam-loop-1032.js").read_text(encoding="utf8")
        cp = (ROOT / "static/learner-slide-checkpoints-1011.js").read_text(encoding="utf8")
        self.assertIn("LearnerBundleCheckpoints", loop)
        self.assertTrue(re.search(r"LearnerBundleCheckpoints\[materialId\]", cp))


class WrongCheckpointPlantsReviewPageTests(unittest.TestCase):
    def test_wrong_first_answer_plants_page_and_correct_does_not(self):
        from unittest.mock import patch
        from teacher_app.checkpoints import service

        item = {"id": "cp1", "materialId": "m1", "page": 4}
        with patch("teacher_app.learning.review_pages.plant") as plant:
            service._plant_review_page({"username": "s1"}, item)
        plant.assert_called_once_with("s1", {"m1": [4]})

    def test_plant_failure_is_swallowed(self):
        from unittest.mock import patch
        from teacher_app.checkpoints import service

        with patch("teacher_app.learning.review_pages.plant", side_effect=RuntimeError("db")):
            service._plant_review_page({"username": "s1"}, {"id": "c", "materialId": "m", "page": 1})
