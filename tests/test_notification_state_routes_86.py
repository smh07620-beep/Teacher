import unittest
from unittest.mock import patch

from flask import Flask, g

from teacher_app.command_center import notification_routes


class NotificationStateRoutes86Tests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__ + str(id(self)))
        self.app.config.update(TESTING=True, SECRET_KEY="notification-state-test")
        self.actor = {"username": "student.bio", "role": "student", "empId": "E100"}

        @self.app.before_request
        def bind_actor():
            g.teacher_user = self.actor

        notification_routes.register_notification_state_routes(self.app)
        self.client = self.app.test_client()

    def test_get_queries_state_for_server_authenticated_actor(self):
        with patch.object(
            notification_routes.notification_state,
            "list_states",
            return_value={"exam:q-1:v1": {"readAt": "2026-09-25T00:00:00+00:00"}},
        ) as list_states:
            response = self.client.get(
                "/api/notification-states?key=exam:q-1:v1&key=announcement:a-1:h1"
            )
        self.assertEqual(response.status_code, 200)
        list_states.assert_called_once_with(
            self.actor,
            ["exam:q-1:v1", "announcement:a-1:h1"],
        )

    def test_patch_ignores_any_body_identity_and_uses_session_actor(self):
        with patch.object(
            notification_routes.notification_state,
            "set_read_state",
            return_value={},
        ) as update:
            response = self.client.patch(
                "/api/notification-states",
                json={
                    "username": "someone.else",
                    "keys": ["exam:q-1:v1"],
                    "read": False,
                },
            )
        self.assertEqual(response.status_code, 200)
        update.assert_called_once_with(self.actor, ["exam:q-1:v1"], read=False)

    def test_patch_rejects_non_boolean_read_state(self):
        response = self.client.patch(
            "/api/notification-states",
            json={"keys": ["exam:q-1:v1"], "read": "false"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["code"], "INVALID_NOTIFICATION_READ_STATE")

    def test_patch_rejects_non_array_keys(self):
        response = self.client.patch(
            "/api/notification-states",
            json={"keys": "exam:q-1:v1", "read": True},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["code"], "INVALID_NOTIFICATION_KEYS")


if __name__ == "__main__":
    unittest.main()
