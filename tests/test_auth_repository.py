from unittest.mock import MagicMock
from types import SimpleNamespace

from tests.auth_support import AuthFixture
from teacher_app.auth import repository


class AuthRepositoryTests(AuthFixture):
    def test_lookup_is_parameterized_and_returns_mapping(self):
        self.assertEqual(repository.find_user(self.base, 'teacher1')['emp_id'], 'E001')
        self.assertIsNone(repository.find_user(self.base, "' OR 1=1 --"))

    def test_record_login_persists_only_timestamp(self):
        before = repository.find_user(self.base, 'teacher1')
        repository.record_login(self.base, 'teacher1', 'now')
        after = repository.find_user(self.base, 'teacher1')
        self.assertEqual(after, {**before, 'last_login_at': 'now'})

    def test_postgres_placeholder_and_connection_cleanup(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = {'username': 'teacher1'}
        base = SimpleNamespace(_db_conn=lambda: (conn, 'postgres'))
        self.assertEqual(repository.find_user(base, 'teacher1'), {'username': 'teacher1'})
        conn.execute.assert_called_with('SELECT * FROM user_accounts WHERE username=%s', ('teacher1',))
        conn.close.assert_called_once()
        conn.reset_mock()
        repository.record_login(base, 'teacher1', 'now')
        conn.execute.assert_called_once_with('UPDATE user_accounts SET last_login_at=%s WHERE username=%s', ('now', 'teacher1'))
        conn.commit.assert_called_once()
        conn.close.assert_called_once()

    def test_update_failure_rolls_back_and_closes(self):
        conn = MagicMock()
        conn.execute.side_effect = RuntimeError('db failure')
        with self.assertRaises(RuntimeError):
            repository.record_login(SimpleNamespace(_db_conn=lambda: (conn, 'sqlite')), 'teacher1', 'now')
        conn.rollback.assert_called_once()
        conn.close.assert_called_once()
