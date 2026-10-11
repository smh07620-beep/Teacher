import unittest
from pathlib import Path

from flask import Flask, g

from teacher_app.storage import row_audit
from teacher_app.storage.row_audit import classify, inventory, register_storage_row_audit


def mat(mid, **kw):
    base = {"id": mid, "title": mid, "storageBackend": "mega", "active": True, "courseId": "c1", "storageMeta": {}}
    base.update(kw)
    return base


def narr(mid, source, kind="teacher_narration", **kw):
    return mat(mid, storageMeta={"mediaKind": kind, "sourceMaterialId": source}, **kw)


class ClassifyTests(unittest.TestCase):
    def test_each_kind(self):
        rows = [
            mat("slide"), mat("off", active=False), mat("loose", courseId=""),
            narr("n-ok", "slide"), narr("n-orphan", "deleted-one"), narr("ai-orphan", "gone", kind="ai_narration"),
        ]
        by_id = {r["id"]: r for r in rows}
        got = {r["id"]: classify(r, by_id)[0] for r in rows}
        self.assertEqual(got, {
            "slide": "in_use", "off": "inactive", "loose": "unlinked",
            "n-ok": "narration", "n-orphan": "orphan_narration", "ai-orphan": "orphan_narration",
        })
        self.assertEqual(classify(rows[3], by_id)[1], "slide")

    def test_narration_is_not_flagged_by_missing_course_or_inactive_source_lookup(self):
        rows = [mat("slide"), narr("n", "slide", courseId="")]
        self.assertFalse(inventory(rows)["rows"][0]["needsAttention"])

    def test_inventory_puts_problems_first_and_filters_backend(self):
        rows = [mat("a"), mat("b", active=False), mat("r", storageBackend="r2")]
        data = inventory(rows)
        self.assertEqual(data["total"], 3)
        self.assertEqual(data["attention"], 1)
        self.assertEqual(data["rows"][0]["id"], "b")
        self.assertEqual([r["id"] for r in inventory(rows, "r2")["rows"]], ["r"])


class RouteTests(unittest.TestCase):
    def client(self, user):
        app = Flask(__name__)
        register_storage_row_audit(app, list_materials=lambda: [mat("a"), mat("b", active=False)])

        @app.before_request
        def inject():
            if user:
                g.teacher_user = user

        return app.test_client()

    def test_requires_login_and_storage_permission(self):
        self.assertEqual(self.client(None).get("/api/admin/storage/rows").status_code, 401)
        for role in ("student", "clinical_teacher", "education_admin", "auditor"):
            self.assertEqual(self.client({"username": "x", "role": role}).get("/api/admin/storage/rows").status_code, 403, role)

    def test_system_admin_reads_and_endpoint_is_get_only(self):
        c = self.client({"username": "a", "role": "system_admin"})
        response = c.get("/api/admin/storage/rows?backend=mega")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["attention"], 1)
        self.assertEqual(c.post("/api/admin/storage/rows").status_code, 405)
        self.assertEqual(c.delete("/api/admin/storage/rows").status_code, 405)


class WiringTests(unittest.TestCase):
    def test_panel_present_and_uses_existing_delete_endpoint_without_innerhtml_rows(self):
        src = (Path(__file__).resolve().parents[1] / "static" / "admin-system.js").read_text(encoding="utf-8")
        self.assertIn("/api/admin/storage/rows", src)
        self.assertIn("appendStorageRowsPanel(storage)", src)
        self.assertIn("method:'DELETE'", src)
        block = src[src.index("function appendStorageRowsPanel"):]
        self.assertNotIn("innerHTML", block.split("window.systemStatusCard")[0])

    def test_registered_in_factory(self):
        src = (Path(__file__).resolve().parents[1] / "teacher_app" / "factory.py").read_text(encoding="utf-8")
        self.assertIn("register_storage_row_audit(app)", src)


if __name__ == "__main__":
    unittest.main()
