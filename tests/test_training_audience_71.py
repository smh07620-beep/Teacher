import sqlite3
import unittest
from pathlib import Path
from types import SimpleNamespace

import schema_migrations
from teacher_app.command_center import audience


ROOT = Path(__file__).parents[1]


class TrainingAudienceProfileTests(unittest.TestCase):
    def test_migration_is_additive_and_registered(self):
        versions = [item.version for item in schema_migrations.MIGRATIONS]
        self.assertIn('0071-pgy-learner-audience', versions)
        self.assertEqual(versions.count('0071-pgy-learner-audience'), 1)

    def test_profile_uses_explicit_flag_and_title_without_changing_role(self):
        user = {
            'username': 't001', 'name': '教師甲', 'empId': 'T001',
            'role': 'clinical_teacher', 'roles': ['clinical_teacher'],
            'professionalTitle': '資深醫檢師', 'pgyLearner': True,
        }
        profile = audience.current_profile(user)
        self.assertEqual(profile['role'], 'clinical_teacher')
        self.assertEqual(profile['professionalTitle'], '資深醫檢師')
        self.assertTrue(profile['pgyLearner'])
        self.assertEqual(profile['audience'], 'pgy')

    def test_unknown_audience_fails_closed_to_online(self):
        profile = audience.current_profile({'username':'u1','role':'student'})
        self.assertFalse(profile['pgyLearner'])
        self.assertEqual(profile['audience'], 'online')


class TrainingAudienceAdminApiTests(unittest.TestCase):
    def _base(self, actor):
        conn = sqlite3.connect(':memory:', isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute('CREATE TABLE user_accounts (username TEXT PRIMARY KEY, role TEXT, pgy_learner INTEGER NOT NULL DEFAULT 0)')
        conn.execute("INSERT INTO user_accounts(username, role, pgy_learner) VALUES ('u1','student',0)")
        return SimpleNamespace(
            app=None,
            _db_conn=lambda: conn,
            _current_user=lambda: actor,
            _json_payload=lambda: {},
        ), conn

    def test_admin_can_toggle_explicit_pgy_learner_without_role_mutation(self):
        from flask import Flask
        base, conn = self._base({'username':'admin','role':'system_admin'})
        base.app = Flask(__name__)
        audience.register_training_audience_71(base)
        client = base.app.test_client()
        response = client.patch('/api/users/u1/training-audience', json={'pgyLearner':True})
        self.assertEqual(response.status_code, 200)
        row = conn.execute("SELECT role,pgy_learner FROM user_accounts WHERE username='u1'").fetchone()
        self.assertEqual(row['role'], 'student')
        self.assertEqual(row['pgy_learner'], 1)

    def test_payload_must_be_boolean_and_permission_is_server_side(self):
        from flask import Flask
        base, _ = self._base({'username':'student','role':'student'})
        base.app = Flask(__name__)
        audience.register_training_audience_71(base)
        client = base.app.test_client()
        self.assertEqual(client.patch('/api/users/u1/training-audience', json={'pgyLearner':True}).status_code, 403)


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
