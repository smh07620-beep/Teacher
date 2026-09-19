import json
import unittest
from unittest.mock import patch

from teacher_app.assessments import blueprints


class BlueprintAnalyticsWeightingTests(unittest.TestCase):
    @patch("teacher_app.assessments.blueprints.repository.insert_blueprint")
    def test_create_blueprint_persists_explicit_balanced_policy(self, insert_blueprint):
        result = blueprints.create_blueprint(
            {
                "quizCategoryId": "cat-1",
                "questionCount": 2,
                "quotas": {"difficulty": {"standard": 2}},
                "qualityMode": "balanced",
            },
            username="admin",
        )
        persisted = insert_blueprint.call_args.args[0]
        quotas = json.loads(persisted["quotas"])
        self.assertEqual(quotas["_selectionPolicy"]["mode"], "balanced")
        self.assertEqual(
            quotas["_selectionPolicy"]["version"],
            "analytics-balanced-v1",
        )
        self.assertEqual(result["qualityMode"], "balanced")

    @patch("teacher_app.assessments.blueprints.repository.insert_blueprint_snapshot")
    @patch(
        "teacher_app.assessments.blueprints.analytics_service.balanced_selection_weight",
        return_value=1.25,
    )
    @patch(
        "teacher_app.assessments.blueprints.analytics_service.get_question_analytics",
        return_value={
            "sufficientData": True,
            "difficultyP": 0.7,
            "discriminationD": 0.4,
            "distractorEffectiveness": 1.0,
            "exposureCount": 10,
        },
    )
    @patch("teacher_app.assessments.blueprints.repository.list_recent_blueprint_snapshots", return_value=[])
    @patch("teacher_app.assessments.blueprints.repository.list_blueprint_questions")
    @patch("teacher_app.assessments.blueprints.repository.get_blueprint")
    @patch("teacher_app.assessments.blueprints.repository.get_blueprint_snapshot", return_value=None)
    def test_publish_snapshot_records_policy_metrics_and_question_identity(
        self,
        _existing,
        get_blueprint,
        list_questions,
        _recent,
        _analytics,
        _weight,
        insert_snapshot,
    ):
        get_blueprint.return_value = {
            "id": "bp-1",
            "quiz_category_id": "cat-1",
            "question_count": 1,
            "exclude_recent": 0,
            "quotas": json.dumps({
                "_selectionPolicy": {
                    "mode": "balanced",
                    "version": "analytics-balanced-v1",
                }
            }),
        }
        list_questions.return_value = [{
            "id": "q-1",
            "quiz_category_id": "cat-1",
            "tag": "",
            "question": "題目",
            "question_type": "choice",
            "difficulty": "standard",
            "image_url": "",
            "options": "[\"A\",\"B\"]",
            "correct": 1,
            "answer_config": "{}",
            "explanation": "",
            "active": 1,
            "status": "reviewed",
            "version": 3,
        }]

        payload, status = blueprints.publish_blueprint("bp-1")
        self.assertEqual(status, 201)
        self.assertEqual(payload["qualityMode"], "balanced")
        stored = insert_snapshot.call_args.args[0]
        question = json.loads(stored["questions"])[0]
        self.assertEqual(question["version"], 3)
        self.assertRegex(question["questionHash"], r"^[0-9a-f]{64}$")
        self.assertEqual(question["selection"]["policyVersion"], "analytics-balanced-v1")
        self.assertEqual(question["selection"]["weight"], 1.25)
        self.assertTrue(question["selection"]["metrics"]["sufficientData"])


if __name__ == "__main__":
    unittest.main()
