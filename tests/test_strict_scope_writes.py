import unittest
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask, g, jsonify

from teacher_app.common import scope, scope_filter
from teacher_app.common.errors import ApiError
from teacher_app.courses import bundle
from teacher_app.materials import job_commit


class StrictScopeValueTests(unittest.TestCase):
    def test_read_normalizers_keep_legacy_fallback(self):
        self.assertEqual(scope.normalize_group("unknown"), scope.DEFAULT_GROUP)
        self.assertEqual(scope.normalize_area("unknown"), scope.DEFAULT_TRAINING_AREA)

    def test_write_validators_reject_unknown_or_blank_explicit_values(self):
        with self.assertRaises(ValueError):
            scope.validate_group("unknown", default=None)
        with self.assertRaises(ValueError):
            scope.validate_group("", default=None)
        with self.assertRaises(ValueError):
            scope.validate_area("unknown", default=None)
        with self.assertRaises(ValueError):
            scope.validate_area("", default=None)

    def test_write_validators_allow_intentional_create_defaults(self):
        self.assertEqual(scope.validate_group(None), scope.DEFAULT_GROUP)
        self.assertEqual(scope.validate_area(None), scope.DEFAULT_TRAINING_AREA)


class StrictScopeRequestGuardTests(unittest.TestCase):
    def _app(self, actor=None):
        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY="scope-test")
        actor = actor or {
            "username": "admin",
            "role": "system_admin",
            "roles": ["system_admin"],
            "preferredGroup": "grpBio",
        }

        @app.before_request
        def bind_actor():
            g.teacher_user = actor

        scope_filter.register_scope_filter(app)

        @app.post("/probe")
        def probe():
            return jsonify({"ok": True})

        return app

    def test_invalid_group_is_400_even_for_system_admin(self):
        response = self._app().test_client().post("/probe", json={"group": "grpDoesNotExist"})
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.get_json()["invalidScope"])

    def test_invalid_area_is_400(self):
        response = self._app().test_client().post("/probe", json={"area": "external"})
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.get_json()["invalidScope"])

    def test_preferred_scope_fields_are_also_strict(self):
        client = self._app().test_client()
        self.assertEqual(
            client.patch("/probe", json={"preferredGroup": "wrong"}).status_code,
            405,
        )
        response = client.post("/probe", json={"preferredArea": "wrong"})
        self.assertEqual(response.status_code, 400)

    def test_valid_scope_passes(self):
        response = self._app().test_client().post(
            "/probe",
            json={"group": "grpMicro", "area": "internal"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])

    def test_anonymous_request_is_left_for_route_auth_boundary(self):
        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY="scope-test")
        scope_filter.register_scope_filter(app)

        @app.post("/probe")
        def probe():
            return jsonify({"routeReached": True})

        response = app.test_client().post("/probe", json={"group": "wrong"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["routeReached"])


class StrictScopeDomainTests(unittest.TestCase):
    def test_course_bundle_rejects_invalid_explicit_scope(self):
        with self.assertRaises(ApiError) as ctx:
            bundle._request_core(
                {
                    "workflowId": "scope-test-123456",
                    "group": "bad-group",
                    "area": "internal",
                    "title": "Course",
                    "examMode": "later",
                }
            )
        self.assertEqual(ctx.exception.status, 400)
        self.assertEqual(ctx.exception.code, "INVALID_SCOPE")

    def test_worker_commit_does_not_default_malformed_scope(self):
        job = {
            "materialId": "m1",
            "payload": {
                "materialId": "m1",
                "originalName": "note.txt",
                "group": "bad-group",
                "area": "internal",
            },
        }
        result = {
            "storageBackend": "local",
            "storageFilename": "source.txt",
            "pageCount": 0,
            "storageMeta": {},
        }
        with patch.object(job_commit.material_repository, "get_material", return_value=None), patch.object(
            job_commit.material_repository, "insert_material"
        ) as insert_material:
            with self.assertRaises(ValueError):
                job_commit.commit(job, result)
        insert_material.assert_not_called()


if __name__ == "__main__":
    unittest.main()
