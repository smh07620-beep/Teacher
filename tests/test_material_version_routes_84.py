import unittest
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask, g

from teacher_app.materials import routes


class MaterialVersionRoute84Tests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__ + str(id(self)))
        self.app.config.update(TESTING=True, SECRET_KEY="material-version-route-test")
        self.actor = {
            "username": "leader.bio",
            "role": "group_leader",
            "roles": ["group_leader"],
            "preferredGroup": "grpBio",
        }

        @self.app.before_request
        def bind_actor():
            g.teacher_user = self.actor

        routes.register_material_catalog_routes(
            self.app,
            paths=SimpleNamespace(),
            storage_runtime=object(),
        )
        self.client = self.app.test_client()

    def test_group_leader_can_publish_version_for_own_group(self):
        before = {
            "id": "mat-bio",
            "title": "Bio SOP",
            "group": "grpBio",
            "area": "internal",
            "currentVersion": 1,
            "requiredCompletionVersion": 1,
            "active": True,
        }
        after = {**before, "currentVersion": 2, "requiredCompletionVersion": 2}
        with patch.object(routes.repository, "get_material", side_effect=[before, before, after]), patch.object(
            routes.service,
            "publish_material_version",
            return_value={
                "ok": True,
                "material": after,
                "version": 2,
                "requiredCompletionVersion": 2,
                "requiresRetraining": True,
            },
        ) as publish, patch.object(routes.audit, "record_event"):
            response = self.client.post(
                "/api/slides/mat-bio/versions",
                json={"changeReason": "重大 SOP 修訂", "requiresRetraining": True},
            )
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        publish.assert_called_once()

    def test_group_leader_cannot_publish_version_for_another_group(self):
        cross_group = {
            "id": "mat-hema",
            "title": "Hema SOP",
            "group": "grpHema",
            "area": "internal",
            "currentVersion": 1,
            "requiredCompletionVersion": 1,
            "active": True,
        }
        with patch.object(routes.repository, "get_material", return_value=cross_group), patch.object(
            routes.service,
            "publish_material_version",
        ) as publish:
            response = self.client.post(
                "/api/slides/mat-hema/versions",
                json={"changeReason": "重大 SOP 修訂", "requiresRetraining": True},
            )
        self.assertEqual(response.status_code, 403, response.get_data(as_text=True))
        self.assertEqual(response.get_json()["error"], "此資源不在你的授權範圍。")
        publish.assert_not_called()


if __name__ == "__main__":
    unittest.main()
