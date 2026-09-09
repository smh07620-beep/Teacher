from unittest.mock import patch

from teacher_app import create_app
from teacher_app.auth import service
from tests.auth_support import AuthFixture
import production_hardening as hardening


class AuthRouteTests(AuthFixture):
    def test_login_success_me_and_logout_contract(self):
        self.assertEqual(self.client.get('/api/auth/me').get_json(), {'authenticated': False, 'user': None})
        result = self.login()
        self.assertEqual(result.status_code, 200)
        body = result.get_json()
        self.assertEqual(set(body), {'ok', 'user'})
        self.assertEqual(set(body['user']), {'username', 'name', 'empId', 'role', 'legacyRole', 'preferredArea',
                                          'preferredGroup', 'active', 'createdAt', 'updatedAt', 'lastLoginAt'})
        self.assertEqual(self.client.get('/api/auth/me').get_json(), {'authenticated': True, 'user': body['user']})
        self.assertEqual(self.client.post('/api/auth/logout').get_json(), {'ok': True})
        self.assertEqual(self.client.get('/api/auth/me').get_json(), {'authenticated': False, 'user': None})
        self.assertEqual(self.client.post('/api/auth/logout').get_json(), {'ok': True})

    def test_wrong_password_missing_and_inactive_contract(self):
        for data in ({'password': 'wrong'}, {'username': 'missing'}):
            result = self.login(**data)
            self.assertEqual(result.status_code, 401)
            self.assertEqual(result.get_json(), {'error': '帳號或密碼不正確，請洽管理者。'})
        self.sql('UPDATE user_accounts SET active=0')
        result = self.login()
        self.assertEqual(result.status_code, 401)
        self.assertEqual(result.get_json(), {'error': '帳號或密碼不正確，請洽管理者。'})

    def test_legacy_password_update_invalidates_session(self):
        self.login()
        response = self.client.patch('/api/users/teacher1', json={'password': 'new-password'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get('/api/auth/me').get_json(), {'authenticated': False, 'user': None})
        self.assertEqual(self.login().status_code, 401)
        self.assertEqual(self.login(password='new-password').status_code, 200)

    def test_legacy_deactivation_invalidates_session(self):
        self.login()
        self.assertEqual(self.client.patch('/api/users/teacher1', json={'active': False}).status_code, 200)
        self.assertEqual(self.client.get('/api/auth/me').get_json(), {'authenticated': False, 'user': None})
        self.assertEqual(self.login().status_code, 401)

    def test_adapter_calls_service(self):
        with patch.object(service, 'login', return_value={'ok': True, 'user': {'username': 'probe'}}) as login:
            self.assertEqual(self.login().get_json()['user']['username'], 'probe')
            self.assertIs(login.call_args.args[0], self.base)
        with patch.object(service, 'current_user', return_value=None) as current:
            self.assertFalse(self.client.get('/api/auth/me').get_json()['authenticated'])
            current.assert_called_once()
        with patch.object(service, 'logout', return_value={'ok': True}) as logout:
            self.client.post('/api/auth/logout')
            logout.assert_called_once()

    def test_factory_blueprint_uses_same_contract(self):
        app = create_app()
        app.config.update(TESTING=True, AUTH_BASE=self.base)
        client = app.test_client()
        self.assertEqual(client.get('/api/auth/me').get_json(), {'authenticated': False, 'user': None})
        response = client.post('/api/auth/login', json={'username': 'teacher1', 'password': self.password})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.get_json()), {'ok', 'user'})
        response = client.post('/api/auth/login', json={'username': 'teacher1', 'password': 'wrong'})
        self.assertEqual(response.get_json(), {'error': '帳號或密碼不正確，請洽管理者。'})
        self.assertEqual(client.post('/api/auth/logout').get_json(), {'ok': True})

    def test_retained_legacy_implementation_matches_adapter(self):
        self.app.add_url_rule('/old/login', view_func=self.base._legacy_api_auth_login, methods=['POST'])
        self.app.add_url_rule('/old/me', view_func=self.base._legacy_api_auth_me)
        self.app.add_url_rule('/old/logout', view_func=self.base._legacy_api_auth_logout, methods=['POST'])
        for password in (self.password, 'wrong'):
            old = self.client.post('/old/login', json={'username': 'teacher1', 'password': password})
            new = self.login(password=password)
            self.assertEqual(old.status_code, new.status_code)
            a, b = old.get_json(), new.get_json()
            if 'user' in a:
                a['user'].pop('lastLoginAt')
                b['user'].pop('lastLoginAt')
            self.assertEqual(a, b)
        self.assertEqual(self.client.get('/old/me').get_json(), self.client.get('/api/auth/me').get_json())
        self.assertEqual(self.client.post('/old/logout').get_json(), self.client.post('/api/auth/logout').get_json())
        raw = dict(self.sql('SELECT * FROM user_accounts')[0])
        self.assertEqual(service.public_user(self.base, raw), self.base._legacy_user_public(raw))


class AuthRateLimitTests(AuthFixture):
    def setUp(self):
        super().setUp()
        # Production owns a process-wide limiter; tests replace it locally.
        state = patch.object(hardening, '_LOGIN_FAILURES', {})
        state.start()
        self.addCleanup(state.stop)
        with patch.dict('os.environ', {'LOGIN_RATE_LIMIT_MAX_ATTEMPTS': '3', 'CSRF_ORIGIN_CHECK': 'true',
                                      'PRODUCTION_REQUIRE_SECRET': 'false', 'SESSION_COOKIE_SECURE': 'false'}):
            hardening.register_production_hardening(self.base)

    def post(self, password='wrong'):
        return self.client.post('/api/auth/login', json={'username': 'teacher1', 'password': password},
                                headers={'Origin': 'http://localhost'})

    def test_rate_limit_contract_expiry_and_success_reset(self):
        with patch.object(hardening.time, 'time', return_value=1000):
            for _ in range(3):
                self.assertEqual(self.post().status_code, 401)
            response = self.post(self.password)
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response.get_json(), {'error': '登入失敗次數過多，請 5 秒後再試。', 'retryAfter': 5})
            self.assertEqual(response.headers['Retry-After'], '5')
        with patch.object(hardening.time, 'time', return_value=1006):
            self.assertEqual(self.post(self.password).status_code, 200)
            self.assertEqual(hardening._LOGIN_FAILURES, {})

    def test_origin_rejection_does_not_count_as_bad_password(self):
        self.assertEqual(self.login().status_code, 403)
        self.assertEqual(hardening._LOGIN_FAILURES, {})

    def test_success_resets_failures_before_threshold(self):
        self.assertEqual(self.post().status_code, 401)
        self.assertEqual(self.post(self.password).status_code, 200)
        self.assertEqual(hardening._LOGIN_FAILURES, {})
