import unittest

from flask import Flask, jsonify

from sensitive_elevation_69 import register_sensitive_elevation_69


class FakeBase:
    def __init__(self, role="system_admin"):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="sensitive-elevation-test")
        self.role = role
        self.guard_calls = []

        routes = (
            ("/api/users/<username>", "user_update", ["PATCH"]),
            ("/api/users", "user_list", ["GET"]),
            ("/api/storage/migrate-to-mega", "storage_migrate", ["POST"]),
            ("/api/maintenance/backup", "backup", ["GET"]),
            ("/api/maintenance/restore", "restore", ["POST"]),
            ("/api/records", "records_delete", ["DELETE"]),
            ("/api/courses", "course_create", ["POST"]),
        )
        for path, endpoint, methods in routes:
            self.app.add_url_rule(path, endpoint, lambda **_kwargs: jsonify({"ok": True}), methods=methods)

    def _current_user(self):
        return {"username": "tester", "role": self.role, "roles": [self.role]}

    def require_elevated_permission(self, *permissions):
        self.guard_calls.append(tuple(permissions))
        return jsonify({"error": "elevation", "elevationRequired": True}), 428


class SensitiveElevation69Tests(unittest.TestCase):
    def client(self, role="system_admin"):
        base = FakeBase(role)
        register_sensitive_elevation_69(base)
        return base, base.app.test_client()

    def test_user_mutation_requires_elevation(self):
        base, client = self.client()
        response = client.patch("/api/users/abc", json={"displayName": "A"})
        self.assertEqual(response.status_code, 428)
        self.assertTrue(response.get_json()["elevationRequired"])
        self.assertEqual(base.guard_calls, [("user.manage",)])

    def test_storage_migration_requires_elevation(self):
        base, client = self.client()
        response = client.post("/api/storage/migrate-to-mega")
        self.assertEqual(response.status_code, 428)
        self.assertEqual(base.guard_calls, [("storage.manage",)])

    def test_backup_and_restore_accept_education_admin_permission_before_elevation(self):
        base, client = self.client("education_admin")
        download = client.get("/api/maintenance/backup")
        restore = client.post("/api/maintenance/restore")
        self.assertEqual(download.status_code, 428)
        self.assertEqual(restore.status_code, 428)
        self.assertEqual(
            base.guard_calls,
            [
                ("backup.manage", "education.cross_group.manage"),
                ("backup.manage", "education.cross_group.manage"),
            ],
        )

    def test_destructive_record_delete_requires_system_manage_and_elevation(self):
        base, client = self.client()
        response = client.delete("/api/records")
        self.assertEqual(response.status_code, 428)
        self.assertEqual(base.guard_calls, [("system.manage",)])

    def test_read_only_user_list_and_normal_course_work_do_not_require_elevation(self):
        base, client = self.client()
        self.assertEqual(client.get("/api/users").status_code, 200)
        self.assertEqual(client.post("/api/courses", json={"title": "Course"}).status_code, 200)
        self.assertEqual(base.guard_calls, [])

    def test_student_is_rejected_before_elevation(self):
        base, client = self.client("student")
        response = client.patch("/api/users/abc", json={"displayName": "A"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(base.guard_calls, [])


if __name__ == "__main__":
    unittest.main()
