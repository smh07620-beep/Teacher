from teacher_app.common import auth
from teacher_app.common.errors import ApiError
from tests.auth_support import AuthFixture


class CentralRbacTests(AuthFixture):
    def test_signature_allowed_only_to_clinical_teacher_and_alias(self):
        for role in auth.CANONICAL_ROLES | set(auth.LEGACY_ROLE_ALIASES):
            user = {'role': role}
            allowed = role in {'clinical_teacher', 'teacher'}
            self.assertEqual(auth.has_permission(user, 'evaluation.sign'), allowed)
            if allowed:
                self.assertIs(auth.require_permission(user, 'evaluation.sign'), user)
            else:
                with self.assertRaises(ApiError) as error:
                    auth.require_permission(user, 'evaluation.sign')
                self.assertEqual(error.exception.status, 403)

    def test_legacy_role_guard_delegates_to_central_policy(self):
        with self.app.test_request_context('/'):
            user, denied = self.base.require_roles('teacher')
            self.assertIsNone(user)
            self.assertEqual(denied[1], 401)
            self.assertEqual(denied[0].get_json(), {'error': '請先登入後再執行此操作。', 'loginRequired': True})
        self.login()
        for role in auth.CANONICAL_ROLES:
            self.sql('UPDATE user_accounts SET role=?', (role,))
            with self.app.test_request_context('/'):
                from flask import session
                session.update(username='teacher1', session_version=1)
                user, denied = self.base.require_roles('clinical_teacher')
                if role == 'clinical_teacher':
                    self.assertIsNone(denied)
                    self.assertEqual(user['role'], role)
                else:
                    self.assertIsNone(user)
                    self.assertEqual(denied[1], 403)
                    self.assertEqual(denied[0].get_json(), {'error': '權限不足：此操作限臨床教師使用。'})

    def test_anonymous_role_and_permission_checks(self):
        for call in (lambda: auth.require_role(None, 'student'),
                     lambda: auth.require_permission(None, 'course.view')):
            with self.assertRaises(ApiError) as error:
                call()
            self.assertEqual(error.exception.status, 401)
