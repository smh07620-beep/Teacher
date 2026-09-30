from pathlib import Path
import sqlite3
import unittest

import release_contract
from teacher_app.common import content_audience
from teacher_app.learning import access as learning_access
from teacher_app.maintenance.content_audience_migration import content_audience_scope_96
from teacher_app.frontend.assets import ASSET_MANIFEST


ROOT = Path(__file__).resolve().parents[1]


class ContentAudience96Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.factory = ROOT.joinpath("teacher_app", "factory.py").read_text(encoding="utf-8")
        cls.policy = ROOT.joinpath("teacher_app", "common", "content_audience.py").read_text(encoding="utf-8")
        cls.guard = ROOT.joinpath("teacher_app", "common", "content_audience_guard.py").read_text(encoding="utf-8")
        cls.ui = ROOT.joinpath("static", "content-audience-1014.js").read_text(encoding="utf-8")
        cls.migration = ROOT.joinpath("teacher_app", "maintenance", "content_audience_migration.py").read_text(encoding="utf-8")

    def test_release_contract_requires_additive_audience_migration(self):
        self.assertIn("0096-content-audience-scope", release_contract.REQUIRED_MIGRATIONS)
        self.assertLess(
            release_contract.REQUIRED_MIGRATIONS.index("0095-media-audio-jobs"),
            release_contract.REQUIRED_MIGRATIONS.index("0096-content-audience-scope"),
        )
        # 0096 remains a required additive migration even after later schema
        # generations advance REQUIRED_RELEASE_MIGRATION (for example 0097).
        self.assertLessEqual(
            release_contract.REQUIRED_MIGRATIONS.index("0096-content-audience-scope"),
            release_contract.REQUIRED_MIGRATIONS.index(release_contract.REQUIRED_RELEASE_MIGRATION),
        )
        self.assertIn("content_audience_migration", self.factory)
        self.assertLess(
            self.factory.index("content_audience_migration"),
            self.factory.index("app = register_schema_migrations(app)"),
        )

    def test_migration_adds_safe_default_to_materials_and_questions(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE materials(id TEXT PRIMARY KEY, group_key TEXT NOT NULL)")
        conn.execute("CREATE TABLE quiz_questions(id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO materials(id,group_key) VALUES('m1','grpBio')")
        conn.execute("INSERT INTO quiz_questions(id) VALUES('q1')")
        content_audience_scope_96(conn, "sqlite")
        m = conn.execute("SELECT audience_scope,audience_groups FROM materials WHERE id='m1'").fetchone()
        q = conn.execute("SELECT audience_scope,audience_groups FROM quiz_questions WHERE id='q1'").fetchone()
        self.assertEqual(m, ("group_only", "[]"))
        self.assertEqual(q, ("group_only", "[]"))
        # Idempotent rerun must not add duplicate columns.
        content_audience_scope_96(conn, "sqlite")
        material_columns = [row[1] for row in conn.execute("PRAGMA table_info(materials)")]
        self.assertEqual(material_columns.count("audience_scope"), 1)
        self.assertEqual(material_columns.count("audience_groups"), 1)
        conn.close()

    def test_owner_group_and_audience_are_independent(self):
        owner = {"role": "student", "preferredGroup": "grpBio"}
        other = {"role": "student", "preferredGroup": "grpHema"}
        admin = {"role": "education_admin", "preferredGroup": "grpHema"}
        locked = {"ownerGroup": "grpBio", "audienceScope": "group_only", "audienceGroups": []}
        public = {"ownerGroup": "grpBio", "audienceScope": "all_staff", "audienceGroups": []}
        selected = {"ownerGroup": "grpBio", "audienceScope": "multi_group", "audienceGroups": ["grpHema"]}
        self.assertTrue(content_audience.visible_to_user(owner, locked))
        self.assertFalse(content_audience.visible_to_user(other, locked))
        self.assertTrue(content_audience.visible_to_user(other, public))
        self.assertTrue(content_audience.visible_to_user(other, selected))
        self.assertTrue(content_audience.visible_to_user(admin, locked))

    def test_learning_access_honors_shared_material_without_changing_owner(self):
        learner = {"role": "student", "preferredArea": "internal", "preferredGroup": "grpHema"}
        shared = {
            "area": "internal",
            "group": "grpBio",
            "ownerGroup": "grpBio",
            "audienceScope": "multi_group",
            "audienceGroups": ["grpHema"],
        }
        locked = {**shared, "audienceScope": "group_only", "audienceGroups": []}
        wrong_area = {**shared, "area": "pgy"}
        self.assertTrue(learning_access.can_access_learning_item(learner, shared))
        self.assertFalse(learning_access.can_access_learning_item(learner, locked))
        self.assertFalse(learning_access.can_access_learning_item(learner, wrong_area))
        self.assertEqual(learning_access.item_learning_scope(shared), ("internal", "grpBio"))

    def test_backend_has_scope_updates_shared_copy_and_delivery_guard(self):
        for marker in (
            "/api/content-audience/materials/<material_id>",
            "/api/content-audience/questions/<question_id>",
            "/api/content-audience/questions/shared",
            "/api/content-audience/questions/<question_id>/copy",
            "material.audience.update",
            "question.audience.update",
            "question.shared.copy",
            "sharedFromGroup",
        ):
            self.assertIn(marker, self.policy)
        self.assertIn("material.manage", self.policy)
        self.assertIn("question.manage", self.policy)
        self.assertIn("uploaded_slide_image", self.guard)
        self.assertIn("material_preview", self.guard)
        self.assertIn("view_material", self.guard)
        self.assertIn("abort(404)", self.guard)
        self.assertLess(
            self.factory.index("app = register_content_audience(app)"),
            self.factory.index("app = register_content_audience_guard(app)"),
        )

    def test_teacher_ui_exposes_visibility_and_shared_question_import(self):
        self.assertIn("/content-audience-1014.js", ASSET_MANIFEST["system"]["body"])
        for marker in (
            "🔒 本組限定",
            "🌐 全科共用",
            "👥 指定組別",
            "/api/content-audience/${kind}/",
            "/api/content-audience/questions/shared?targetGroup=",
            "/api/content-audience/questions/${encodeURIComponent(source.id)}/copy",
            "原題仍由來源組管理",
            "新教材預設本組限定",
        ):
            self.assertIn(marker, self.ui)
        self.assertNotIn("X-Admin-Key", self.ui)
        self.assertNotIn("getAdminKey", self.ui)


if __name__ == "__main__":
    unittest.main()
