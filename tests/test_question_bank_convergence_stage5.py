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
        cls.blueprints = ROOT.joinpath(
            "teacher_app", "assessments", "blueprints.py"
        ).read_text(encoding="utf-8")
        cls.analytics = ROOT.joinpath(
            "teacher_app", "assessments", "analytics.py"
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

    def test_blueprint_selection_and_snapshot_ownership_is_canonical(self):
        for marker in (
            "def _draw(",
            "def create_blueprint(",
            "def publish_blueprint(",
            "repository.insert_blueprint",
            "repository.get_blueprint_snapshot",
            "repository.list_blueprint_questions",
            "repository.list_recent_blueprint_snapshots",
            "repository.insert_blueprint_snapshot",
        ):
            self.assertIn(marker, self.blueprints)
        for marker in (
            "def insert_blueprint(",
            "def get_blueprint(",
            "def get_blueprint_snapshot(",
            "def list_blueprint_questions(",
            "def list_recent_blueprint_snapshots(",
            "def insert_blueprint_snapshot(",
        ):
            self.assertIn(marker, self.repository)
        self.assertNotIn("def _draw(", self.adapter)
        self.assertNotIn("INSERT INTO exam_blueprints", self.adapter)
        self.assertNotIn("exam_blueprint_snapshots", self.adapter)
        self.assertIn("blueprint_service.create_blueprint", self.adapter)
        self.assertIn("blueprint_service.publish_blueprint", self.adapter)

    def test_question_analytics_ownership_is_canonical(self):
        for marker in (
            "def list_question_attempt_analytics(",
            "def get_bank_question_correct(",
            "question_attempt_analytics",
            "SELECT correct FROM quiz_questions",
        ):
            self.assertIn(marker, self.repository)
        for marker in (
            "MIN_SUFFICIENT_ATTEMPTS = 10",
            "def get_question_analytics(",
            "Counter(",
            '"correctRate"',
            '"optionSelectionCounts"',
            '"distractorDistribution"',
        ):
            self.assertIn(marker, self.analytics)
        self.assertIn("analytics_service.get_question_analytics", self.adapter)
        self.assertNotIn("question_attempt_analytics", self.adapter)
        self.assertNotIn("SELECT correct FROM quiz_questions", self.adapter)
        self.assertNotIn("Counter(", self.adapter)

    def test_root_is_http_rbac_compatibility_adapter(self):
        self.assertIn("HTTP/RBAC compatibility adapter", self.adapter)
        self.assertNotIn("base._db_conn", self.adapter)


if __name__ == "__main__":
    unittest.main()
