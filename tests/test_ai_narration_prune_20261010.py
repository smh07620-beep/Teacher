"""AI voices are auto-pruned to the newest two per source material."""
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

ROOT = Path(__file__).resolve().parents[1]


class PruneWiringTest(unittest.TestCase):
    def test_route_rbac_and_frontend_call_exist(self):
        routes = (ROOT / "teacher_app/materials/routes.py").read_text(encoding="utf-8")
        rbac = (ROOT / "teacher_app/auth/rbac_legacy_adapter.py").read_text(encoding="utf-8")
        js = (ROOT / "static/teacher-media-audio-1014.js").read_text(encoding="utf-8")
        self.assertIn("/api/slides/<slide_id>/prune-ai-narrations", routes)
        self.assertIn("AI_NARRATIONS_KEPT = 2", routes)
        self.assertIn('"api_prune_ai_narrations": ("material.manage", "scoped")', rbac)
        self.assertIn("prune-ai-narrations", js)


class PruneBehaviourTest(unittest.TestCase):
    def test_keeps_newest_two_and_deletes_older(self):
        from teacher_app.materials import routes, repository, service

        def voice(idx):
            return {"id": f"v{idx}", "group": "g", "dateAdded": f"2026-10-0{idx}",
                    "storageMeta": {"mediaKind": "ai_narration", "sourceMaterialId": "src"}}

        rows = [voice(1), voice(2), voice(3), voice(4),
                {"id": "other", "storageMeta": {"mediaKind": "ai_narration", "sourceMaterialId": "elsewhere"}},
                {"id": "src", "storageMeta": {}}]
        deleted = []
        app = Flask(__name__)
        app.secret_key = "x"
        app.config["STORAGE_PATHS"] = object()
        with patch.object(routes, "WebStorageRuntime", lambda paths: object()), \
             patch.object(repository, "get_material", lambda mid: {"id": mid}), \
             patch.object(repository, "list_uploaded_materials", lambda *a, **k: rows), \
             patch.object(service, "delete_material", lambda mid, **k: deleted.append(mid)), \
             patch.object(routes.audit, "record_event", lambda **k: None):
            routes.register_material_catalog_routes(app, paths=object(), storage_runtime=object())
            view = app.view_functions["api_prune_ai_narrations"]
            # bypass auth for the unit test: the closure calls require_admin(); simulate an admin
            with app.test_request_context("/api/slides/src/prune-ai-narrations", method="POST"):
                from flask import g
                g.teacher_user = {"username": "t", "roles": ["education_admin"], "role": "education_admin"}
                response = view("src")
                if isinstance(response, tuple):
                    response = response[0]
                data = response.get_json()
        self.assertEqual(sorted(deleted), ["v1", "v2"])
        self.assertEqual(data["kept"], ["v4", "v3"])


if __name__ == "__main__":
    unittest.main()
