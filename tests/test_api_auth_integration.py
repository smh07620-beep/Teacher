import unittest

from teacher_app.common.auth import has_permission
from tests.auth_support import AuthFixture


class AuthApiIntegrationTests(AuthFixture):
    def test_login_me_logout_full_http_flow(self):
        anonymous = self.client.get("/api/auth/me")

        self.assertEqual(anonymous.status_code, 200)
        self.assertEqual(
            anonymous.get_json(),
            {"authenticated": False, "user": None},
        )

        logged_in = self.login()

        self.assertEqual(logged_in.status_code, 200)

        body = logged_in.get_json()

        self.assertTrue(body["ok"])
        self.assertEqual(
            body["user"]["username"],
            "teacher1",
        )
        self.assertEqual(
            body["user"]["role"],
            "clinical_teacher",
        )

        me = self.client.get("/api/auth/me")

        self.assertEqual(me.status_code, 200)
        self.assertTrue(
            me.get_json()["authenticated"]
        )

        logout = self.client.post(
            "/api/auth/logout"
        )

        self.assertEqual(logout.status_code, 200)
        self.assertEqual(
            logout.get_json(),
            {"ok": True},
        )

        after = self.client.get("/api/auth/me")

        self.assertEqual(
            after.get_json(),
            {"authenticated": False, "user": None},
        )

    def test_session_version_change_invalidates_existing_session(self):
        self.assertEqual(
            self.login().status_code,
            200,
        )

        self.assertTrue(
            self.client.get(
                "/api/auth/me"
            ).get_json()["authenticated"]
        )

        self.sql(
            """
            UPDATE user_accounts
            SET session_version=session_version+1
            WHERE username=?
            """,
            ("teacher1",),
        )

        after = self.client.get(
            "/api/auth/me"
        )

        self.assertEqual(
            after.get_json(),
            {"authenticated": False, "user": None},
        )

    def test_wrong_password_and_inactive_user_keep_legacy_contract(self):
        wrong = self.login(
            password="wrong"
        )

        self.assertEqual(
            wrong.status_code,
            401,
        )
        self.assertEqual(
            wrong.get_json(),
            {
                "error":
                "帳號或密碼不正確，請洽管理者。"
            },
        )

        self.sql(
            """
            UPDATE user_accounts
            SET active=0
            WHERE username=?
            """,
            ("teacher1",),
        )

        inactive = self.login()

        self.assertEqual(
            inactive.status_code,
            401,
        )
        self.assertEqual(
            inactive.get_json(),
            {
                "error":
                "帳號或密碼不正確，請洽管理者。"
            },
        )

    def test_four_character_password_can_create_and_login(self):
        created = self.client.post(
            "/api/users",
            json={
                "username": "user4",
                "password": "1357",
                "name": "Four Digit User",
                "empId": "E004",
                "role": "student",
                "preferredArea": "internal",
                "preferredGroup": "grpBio",
            },
        )

        self.assertEqual(
            created.status_code,
            200,
            created.get_data(as_text=True),
        )

        login = self.client.post(
            "/api/auth/login",
            json={
                "username": "user4",
                "password": "1357",
            },
        )

        self.assertEqual(
            login.status_code,
            200,
            login.get_data(as_text=True),
        )

        self.assertTrue(
            login.get_json()["ok"]
        )

    def test_four_character_password_reset_can_login(self):
        reset = self.client.patch(
            "/api/users/teacher1",
            json={
                "password": "2468",
            },
        )

        self.assertEqual(
            reset.status_code,
            200,
            reset.get_data(as_text=True),
        )

        # Old password must stop working.
        old_login = self.client.post(
            "/api/auth/login",
            json={
                "username": "teacher1",
                "password": self.password,
            },
        )

        self.assertEqual(
            old_login.status_code,
            401,
        )

        # New 4-character password must work immediately.
        new_login = self.client.post(
            "/api/auth/login",
            json={
                "username": "teacher1",
                "password": "2468",
            },
        )

        self.assertEqual(
            new_login.status_code,
            200,
            new_login.get_data(as_text=True),
        )

        self.assertTrue(
            new_login.get_json()["ok"]
        )

    def test_three_character_password_is_rejected(self):
        response = self.client.patch(
            "/api/users/teacher1",
            json={
                "password": "123",
            },
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.assertIn(
            "至少 4 碼",
            response.get_json()["error"],
        )

    def test_evaluation_sign_rbac_invariant(self):
        self.assertTrue(
            has_permission(
                {"role": "clinical_teacher"},
                "evaluation.sign",
            )
        )

        self.assertFalse(
            has_permission(
                {"role": "education_admin"},
                "evaluation.sign",
            )
        )

        self.assertFalse(
            has_permission(
                {"role": "system_admin"},
                "evaluation.sign",
            )
        )


if __name__ == "__main__":
    unittest.main()
