import unittest

from teacher_app.exams.routes import register_legacy_exam_routes
from tests.exam_support import ExamBase, submit_payload


class ExamLegacyRouteTests(unittest.TestCase):
    def setUp(self):
        self.base = ExamBase()
        register_legacy_exam_routes(self.base)
        self.client = self.base.app.test_client()

    def tearDown(self):
        self.base.close()

    def test_login_error_keeps_legacy_contract(self):
        self.base.user = None
        response = self.client.post("/api/exam-attempts", json={"quizCategoryId": "quiz1"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json(), {"error": "請先登入後再進行考核。", "loginRequired": True})

    def test_start_submit_and_duplicate_keep_legacy_contract(self):
        started = self.client.post("/api/exam-attempts", json={"quizCategoryId": "quiz1"})
        self.assertEqual(started.status_code, 201)
        attempt_id = started.get_json()["attemptId"]
        submitted = self.client.post(f"/api/exam-attempts/{attempt_id}/submit", json=submit_payload())
        self.assertEqual(submitted.status_code, 200)
        self.assertEqual(submitted.get_json()["ok"], True)
        duplicate = self.client.post(f"/api/exam-attempts/{attempt_id}/submit", json=submit_payload())
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.get_json(), {"error": "此考核已經提交，不能重複計分。"})


if __name__ == "__main__":
    unittest.main()
