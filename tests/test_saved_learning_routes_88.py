import unittest
from unittest.mock import patch

from flask import Flask, g

from teacher_app.common.errors import ApiError
from teacher_app.learning import saved_service
from teacher_app.learning.saved_routes import register_saved_learning_routes


class SavedLearningRoutes88Tests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="test")
        self.user = {"username": "student.a", "role": "student", "roles": ["student"]}

        @self.app.before_request
        def bind_user():
            g.teacher_user = self.user

        register_saved_learning_routes(self.app)
        self.client = self.app.test_client()

    def test_list_and_update_routes_delegate_to_service(self):
        with patch.object(saved_service, "list_saved_items", return_value=[{"itemType": "material", "itemId": "m1"}]):
            response = self.client.get("/api/saved-learning-items")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["items"][0]["itemId"], "m1")

        with patch.object(saved_service, "set_saved_item", return_value={"ok": True, "itemType": "material", "itemId": "m1", "saved": True}) as setter:
            response = self.client.put("/api/saved-learning-items/material/m1", json={"saved": True})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["saved"])
        self.assertTrue(setter.call_args.kwargs["saved"])

    def test_invalid_state_and_api_error_shape(self):
        response = self.client.put("/api/saved-learning-items/material/m1", json={"saved": "yes"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["code"], "INVALID_SAVED_STATE")

        with patch.object(saved_service, "set_saved_item", side_effect=ApiError("LEARNING_ITEM_NOT_FOUND", "找不到可存取的學習項目。", status=404)):
            response = self.client.put("/api/saved-learning-items/material/missing", json={"saved": True})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["code"], "LEARNING_ITEM_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
