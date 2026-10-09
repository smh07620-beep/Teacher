import unittest
from unittest.mock import patch

from teacher_app.assessments import assignees as exam_assignees
from teacher_app.common.errors import ApiError
from teacher_app.maintenance.exam_assignee_migration import exam_assignees_117
from tests import test_assessment_workflow_identity as base


class ExamAssigneeTests(unittest.TestCase):
    def setUp(self):
        base.AssessmentWorkflowIdentityTests.setUp(self)
        conn, kind = self.connect()
        try:
            exam_assignees_117(conn, kind)
            conn.execute("UPDATE quiz_categories SET active=1, review_status='approved' WHERE id='cat-1'")
        finally:
            conn.close()
        self.admin = dict(self.actor)
        review = patch("teacher_app.exams.records.category_review_summary", return_value={})
        review.start()
        self.addCleanup(review.stop)
        patcher = patch("teacher_app.learning.assignment_service._active_account", side_effect=lambda name: {"username": name} if name in {"alice", "bob"} else None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _as(self, user):
        self.actor.clear()
        self.actor.update(user)

    def _student(self, name, group="grpBio"):
        return {"username": name, "name": name, "role": "student", "roles": ["student"], "preferredGroup": group}

    def test_no_assignees_keeps_existing_behaviour(self):
        self._as(self._student("bob"))
        listed = self.client.get("/api/quiz-categories?group=grpBio&area=internal").get_json()
        self.assertEqual([item["id"] for item in listed], ["cat-1"])

    def test_assigned_user_sees_exam_and_others_do_not(self):
        response = self.client.put("/api/quiz-categories/cat-1/assignees", json={"assignees": [{"type": "user", "key": "alice"}]})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(self.client.get("/api/quiz-categories/cat-1/assignees").get_json()["assignees"][0]["key"], "alice")
        self._as(self._student("bob"))
        self.assertEqual(self.client.get("/api/quiz-categories?group=grpBio&area=internal").get_json(), [])
        self._as(self._student("alice"))
        self.assertEqual(len(self.client.get("/api/quiz-categories?group=grpBio&area=internal").get_json()), 1)

    def test_unassigned_student_cannot_start_exam(self):
        self.client.put("/api/quiz-categories/cat-1/assignees", json={"assignees": [{"type": "user", "key": "alice"}]})
        with self.assertRaises(ApiError) as ctx:
            exam_assignees.assert_can_take(self._student("bob"), "cat-1")
        self.assertEqual(ctx.exception.status, 403)
        exam_assignees.assert_can_take(self._student("alice"), "cat-1")
        exam_assignees.assert_can_take(self.admin, "cat-1")  # 管理者可預覽

    def test_group_assignee_matches_members_only(self):
        self.client.put("/api/quiz-categories/cat-1/assignees", json={"assignees": [{"type": "group", "key": "grpBio"}]})
        exam_assignees.assert_can_take(self._student("bob", "grpBio"), "cat-1")
        with self.assertRaises(ApiError):
            exam_assignees.assert_can_take(self._student("carol", "grpMicro"), "cat-1")

    def test_student_cannot_change_assignees(self):
        self._as(self._student("bob"))
        response = self.client.put("/api/quiz-categories/cat-1/assignees", json={"assignees": []})
        self.assertIn(response.status_code, {401, 403})
        self.assertEqual(exam_assignees.list_assignees("cat-1"), [])

    def test_unknown_user_and_bad_group_are_rejected(self):
        bad_user = self.client.put("/api/quiz-categories/cat-1/assignees", json={"assignees": [{"type": "user", "key": "ghost"}]})
        self.assertEqual(bad_user.status_code, 400)
        bad_group = self.client.put("/api/quiz-categories/cat-1/assignees", json={"assignees": [{"type": "group", "key": "nope"}]})
        self.assertEqual(bad_group.status_code, 400)

    def test_clearing_list_restores_default_visibility(self):
        self.client.put("/api/quiz-categories/cat-1/assignees", json={"assignees": [{"type": "user", "key": "alice"}]})
        self.client.put("/api/quiz-categories/cat-1/assignees", json={"assignees": []})
        self._as(self._student("bob"))
        self.assertEqual(len(self.client.get("/api/quiz-categories?group=grpBio&area=internal").get_json()), 1)


if __name__ == "__main__":
    unittest.main()
