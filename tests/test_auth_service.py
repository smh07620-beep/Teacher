from unittest.mock import patch
from flask.sessions import SecureCookieSession

from tests.auth_support import AuthFixture
from teacher_app.auth import service
from teacher_app.common.errors import ApiError


class AuthServiceTests(AuthFixture):
    def test_login_success_clears_old_session_and_records_timestamp(self):
        session = SecureCookieSession({'stale': 'value'})
        result = service.login(self.base, {'username': ' Teacher1 ', 'password': self.password}, session)
        self.assertEqual(set(session), {'_permanent', 'username', 'session_version'})
        self.assertTrue(session.permanent)
        self.assertEqual(session['session_version'], 1)
        self.assertEqual(result['user']['role'], 'clinical_teacher')
        self.assertEqual(result['user']['legacyRole'], 'teacher')
        self.assertEqual(result['user']['lastLoginAt'], self.sql('SELECT last_login_at FROM user_accounts')[0][0])

    def test_bad_credentials_and_inactive_are_indistinguishable(self):
        for data in ({'username': 'missing', 'password': self.password},
                     {'username': 'teacher1', 'password': 'wrong'}):
            with self.assertRaises(ApiError) as error:
                service.login(self.base, data, SecureCookieSession())
            self.assertEqual(error.exception.status, 401)
            self.assertEqual(error.exception.message, '帳號或密碼不正確，請洽管理者。')
        self.sql('UPDATE user_accounts SET active=0')
        with self.assertRaises(ApiError) as error:
            service.login(self.base, {'username': 'teacher1', 'password': self.password}, SecureCookieSession())
        self.assertEqual(error.exception.status, 401)
        self.assertEqual(self.sql('SELECT last_login_at FROM user_accounts')[0][0], '')

    def test_failed_persistence_does_not_authenticate(self):
        session = SecureCookieSession({'stale': 'value'})
        with patch('teacher_app.auth.repository.record_login', side_effect=RuntimeError('db failure')):
            with self.assertRaises(RuntimeError):
                service.login(self.base, {'username': 'teacher1', 'password': self.password}, session)
        self.assertEqual(dict(session), {'stale': 'value'})

    def test_missing_deleted_inactive_and_malformed_sessions(self):
        self.assertIsNone(service.current_user(self.base, SecureCookieSession()))
        for version in (0, 2, 'invalid', None):
            session = SecureCookieSession({'username': 'teacher1', 'session_version': version})
            self.assertIsNone(service.current_user(self.base, session))
            self.assertEqual(dict(session), {})
        for query in ('UPDATE user_accounts SET active=0', 'DELETE FROM user_accounts'):
            self.sql(query)
            session = SecureCookieSession({'username': 'teacher1', 'session_version': 1})
            self.assertIsNone(service.current_user(self.base, session))
            self.assertFalse(session)

    def test_current_user_uses_fresh_role(self):
        session = SecureCookieSession({'username': 'teacher1', 'session_version': 1})
        self.sql("UPDATE user_accounts SET role='auditor'")
        self.assertEqual(service.current_user(self.base, session)['role'], 'auditor')

    def test_logout_is_idempotent(self):
        session = SecureCookieSession({'username': 'teacher1', 'session_version': 1})
        self.assertEqual(service.logout(session), {'ok': True})
        self.assertFalse(session)
        self.assertEqual(service.logout(session), {'ok': True})
