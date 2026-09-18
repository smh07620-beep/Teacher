"""Ownership guards for Stage 5 Question Bank convergence."""
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class QuestionBankConvergenceStage5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = ROOT.joinpath("question_bank_68.py").read_text(encoding="utf-8")
        cls.service = ROOT.joinpath(
            "teacher_app", "assessments", "question_bank.py"
        ).read_text(encoding="utf-8")
        cls.repository = ROOT.joinpath(
            "teacher_app", "assessments", "repository.py"
        ).read_text(encoding="utf-8")

    def test_assessment_repository_owns_bank_crud_and_review_sql(self):
        for marker in (
            "def list_bank_questions(",
            "def get_bank_question(",
            "def list_duplicate_candidates(",
            "def insert_bank_question(",
            "def update_bank_question(",
            "def delete_bank_question(",
            "def review_bank_question(",
        ):
            self.assertIn(marker, self.repository)
        for sql in (
            "INSERT INTO quiz_questions(",
            "UPDATE quiz_questions SET question=",
            "DELETE FROM quiz_questions WHERE id=",
            "reviewed_by=",
        ):
            self.assertNotIn(sql, self.adapter)

    def test_question_bank_service_owns_validation_projection_and_duplicates(self):
        for marker in (
            "def normalized(",
            "def similarity(",
            "def metadata(",
            "def question_payload(",
            "def create_draft(",
            "def list_questions(",
            "def update_question(",
            "def delete_question(",
            "def review_question(",
        ):
            self.assertIn(marker, self.service)
        self.assertNotIn("from flask", self.service)
        self.assertNotIn("base.", self.service)

    def test_root_routes_delegate_bank_crud_and_review(self):
        for marker in (
            "bank_service.create_draft",
            "bank_service.list_questions",
            "bank_service.update_question",
            "bank_service.delete_question",
            "bank_service.review_question",
        ):
            self.assertIn(marker, self.adapter)

    def test_blueprint_and_analytics_debt_remains_explicit(self):
        self.assertIn("def _draw(", self.adapter)
        self.assertIn("INSERT INTO exam_blueprints", self.adapter)
        self.assertIn("question_attempt_analytics", self.adapter)
        self.assertIn("exam_blueprint_snapshots", self.adapter)


if __name__ == "__main__":
    unittest.main()
