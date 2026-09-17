"""Teacher 7.1 explicit PGY learner audience and presentation-title contracts."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

import schema_migrations
from teacher_app.command_center import audience


ROOT = Path(__file__).parents[1]


class TrainingAudienceProfileTests(unittest.TestCase):
    def test_migration_is_additive_and_registered(self):
        versions = [version for version, _fn in schema_migrations.MIGRATIONS]
        self.assertIn("0071-pgy-learner-audience", versions)
        source = ROOT.joinpath("teacher_app", "command_center", "audience.py").read_text(encoding="utf-8")
        self.assertIn("pgy_learner", source)
        self.assertIn("NOT NULL DEFAULT", source)

    def test_profile_uses_explicit_flag_and_title_without_changing_role(self):
        user = {
            "username": "u1",
            "name": "王小明",
            "empId": "E001",
            "role": "student",
            "pgyLearner": True,
            "professionalTitle": "資深醫檢師",
        }
        with patch.object(audience, "_row_for_username", return_value={}):
            profile = audience.current_profile(user)
        self.assertTrue(profile["pgyLearner"])
        self.assertEqual(profile["audience"], "pgy")
        self.assertEqual(profile["professionalTitle"], "資深醫檢師")
        self.assertEqual(profile["role"], "student")

    def test_unknown_audience_fails_closed_to_online(self):
        with patch.object(audience, "_row_for_username", return_value={}):
            profile = audience.current_profile({"username":"u2","role":"student"})
        self.assertFalse(profile["pgyLearner"])
        self.assertEqual(profile["audience"], "online")


class TrainingAudienceAdminApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / "audience.db")
        conn = sqlite3.connect(self.path)
        conn.execute("CREATE TABLE user_accounts(username TEXT PRIMARY KEY,pgy_learner INTEGER NOT NULL DEFAULT 0)")
        conn.execute("INSERT INTO user_accounts(username,pgy_learner) VALUES('learner1',0)")
        conn.commit()
        conn.close()

        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="test")
        self.actor = {"username":"admin","role":"system_admin"}

        def connect():
            c = sqlite3.connect(self.path)
            c.row_factory = sqlite3.Row
            c.isolation_level = None
            return c, "sqlite"

        self.base = SimpleNamespace(app=self.app, _current_user=lambda: self.actor, _db_conn=connect)
        audience.register_training_audience_71(self.base)
        self.client = self.app.test_client()

    def test_admin_can_toggle_explicit_pgy_learner_without_role_mutation(self):
        self.assertFalse(self.client.get('/api/users/learner1/training-audience').get_json()['pgyLearner'])
        response = self.client.patch('/api/users/learner1/training-audience', json={'pgyLearner': True})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['pgyLearner'])
        self.assertTrue(self.client.get('/api/users/learner1/training-audience').get_json()['pgyLearner'])

    def test_payload_must_be_boolean_and_permission_is_server_side(self):
        self.assertEqual(self.client.patch('/api/users/learner1/training-audience', json={'pgyLearner':'yes'}).status_code, 400)
        self.actor = {"username":"student","role":"student"}
        self.assertEqual(self.client.get('/api/users/learner1/training-audience').status_code, 403)


class TrainingAudienceFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.people = ROOT.joinpath('static','admin-people.js').read_text(encoding='utf-8')
        cls.home_badge = ROOT.joinpath('static','home-profile-title-71.js').read_text(encoding='utf-8')
        cls.frontend = ROOT.joinpath('pgy_frontend.py').read_text(encoding='utf-8')
        cls.entrypoint = ROOT.joinpath('pgy_app.py').read_text(encoding='utf-8')

    def test_people_editor_exposes_explicit_pgy_checkbox(self):
        self.assertIn('admin-user-editor-pgy-learner', self.people)
        self.assertIn('/training-audience', self.people)
        self.assertIn('不會授予教師簽核、組長複核或管理權限', self.people)
        self.assertIn('professionalTitle', self.people)

    def test_signed_in_header_uses_professional_title_then_role_fallback(self):
        self.assertIn('/api/training-command-center/profile', self.home_badge)
        self.assertIn('function displayTitle(profile)', self.home_badge)
        self.assertIn("profile?.professionalTitle", self.home_badge)
        self.assertIn("priority=['system_admin','education_admin','group_leader','clinical_teacher','auditor','student']", self.home_badge)
        self.assertIn('data-teacher-title-badge', self.home_badge)
        self.assertIn('工號 ${emp}', self.home_badge)
        self.assertIn('/home-profile-title-71.js?v=7113', self.frontend)

    def test_entrypoint_registers_audience_after_migration_runner(self):
        self.assertIn('register_training_audience_71', self.entrypoint)
        self.assertLess(self.entrypoint.index('register_schema_migrations(legacy_app)'), self.entrypoint.index('register_training_audience_71(legacy_app)'))


if __name__ == '__main__':
    unittest.main()
