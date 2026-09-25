import contextlib
import sqlite3
import unittest
from unittest.mock import patch

import release_contract
import schema_migrations
from teacher_app.command_center import notification_state
from teacher_app.common import db as common_db
from teacher_app.common.errors import ApiError
from teacher_app.maintenance.notification_state_migration import notification_read_state_86


class NotificationReadState86Tests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        notification_read_state_86(self.conn, "sqlite")
        self.user_a = {"username": "student.a"}
        self.user_b = {"username": "student.b"}

    def tearDown(self):
        self.conn.close()

    @contextlib.contextmanager
    def _read(self):
        yield self.conn, "sqlite"

    @contextlib.contextmanager
    def _tx(self):
        try:
            yield self.conn, "sqlite"
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def test_release_contract_registers_0086_once_after_0084(self):
        versions = [version for version, _fn in schema_migrations.MIGRATIONS]
        self.assertEqual(versions.count("0086-notification-read-state"), 1)
        self.assertEqual(release_contract.REQUIRED_MIGRATIONS[-1], "0086-notification-read-state")
        self.assertLess(
            release_contract.REQUIRED_MIGRATIONS.index("0084-material-version-retraining"),
            release_contract.REQUIRED_MIGRATIONS.index("0086-notification-read-state"),
        )

    def test_read_state_is_per_user_and_can_be_marked_unread_again(self):
        key = "remediation:quiz-1:record-2"
        with patch.object(common_db, "read_connection", self._read), patch.object(
            common_db, "transaction", self._tx
        ):
            result = notification_state.set_read_state(self.user_a, [key], read=True)
            self.assertIn(key, result)
            self.assertTrue(result[key]["readAt"])
            self.assertEqual(notification_state.list_states(self.user_b, [key]), {})
            self.assertIn(key, notification_state.list_states(self.user_a, [key]))

            result = notification_state.set_read_state(self.user_a, [key], read=False)
            self.assertEqual(result, {})
            self.assertEqual(notification_state.list_states(self.user_a, [key]), {})

    def test_new_event_key_does_not_inherit_old_read_state(self):
        first = "remediation:quiz-1:record-1"
        second = "remediation:quiz-1:record-2"
        with patch.object(common_db, "read_connection", self._read), patch.object(
            common_db, "transaction", self._tx
        ):
            notification_state.set_read_state(self.user_a, [first], read=True)
            states = notification_state.list_states(self.user_a, [first, second])
        self.assertIn(first, states)
        self.assertNotIn(second, states)

    def test_invalid_or_unbounded_keys_fail_closed(self):
        with self.assertRaises(ApiError) as invalid:
            notification_state.normalize_keys(["bad\nkey"])
        self.assertEqual(invalid.exception.code, "INVALID_NOTIFICATION_KEY")

        with self.assertRaises(ApiError) as too_many:
            notification_state.normalize_keys([f"exam:q-{index}:v1" for index in range(51)])
        self.assertEqual(too_many.exception.code, "TOO_MANY_NOTIFICATION_KEYS")

    def test_missing_authenticated_username_is_rejected(self):
        with self.assertRaises(ApiError) as caught:
            notification_state.list_states(None, ["exam:q-1:v1"])
        self.assertEqual(caught.exception.status, 401)


if __name__ == "__main__":
    unittest.main()
