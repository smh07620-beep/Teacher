import json
import unittest
from pathlib import Path

import schema_migrations
from multi_role_66 import register_multi_role_66
from tests.auth_support import AuthFixture


class UserProfileEditorFrontend681Tests(unittest.TestCase):
    def test_existing_account_editor_exposes_profile_metadata_without_role_mutation(self):
        source = Path(__file__).parents[1].joinpath('static', 'admin-people.js').read_text(encoding='utf-8')
        self.assertIn('async function openAdminUserEditor(username)', source)
        self.assertIn('admin-user-editor-professional-title', source)
        self.assertIn('admin-user-editor-responsibility-tags', source)
        self.assertIn('admin-user-editor-pgy-learner', source)
        self.assertIn('professionalTitle', source)
        self.assertIn('responsibilityTags', source)
        self.assertIn('pgyLearner', source)
        start = source.index('async function saveAdminUserEditor()')
        end = source.index('window.adminProfileTags', start)
        save = source[start:end]
        self.assertIn('const payload={name,empId,professionalTitle,responsibilityTags}', save)
        self.assertIn('/training-audience', save)
        self.assertNotIn('role:', save)
        self.assertNotIn('roles:', save)
        self.assertIn('職稱、職責標籤與 PGY 學員分類都不參與 RBAC 判斷', source)
        self.assertIn('不會授予教師簽核、組長複核或管理權限', source)

    def test_account_list_shows_profile_metadata_and_edit_action(self):
        source = Path(__file__).parents[1].joinpath('static', 'admin-people.js').read_text(encoding='utf-8')
        self.assertIn('編輯人員資料', source)
        self.assertIn('u.professionalTitle', source)
        self.assertIn('adminProfileTags(u.responsibilityTags)', source)


class UserProfileEditorApi681Tests(AuthFixture):
    def setUp(self):
        super().setUp()
        conn, _ = self.connect()
        try:
            schema_migrations._additive_rbac_pgy_signing_66(conn, "sqlite")
            conn.execute("ALTER TABLE user_accounts ADD COLUMN professional_title TEXT NOT NULL DEFAULT ''")
            conn.execute("ALTER TABLE user_accounts ADD COLUMN responsibility_tags TEXT NOT NULL DEFAULT '[]'")
        finally:
            conn.close()
        register_multi_role_66(self.base)
        self.sql(
            "UPDATE user_accounts SET role=?, roles_json=? WHERE username=?",
            ('clinical_teacher', json.dumps(['clinical_teacher', 'group_leader']), 'teacher1'),
        )

    def test_profile_patch_roundtrips_without_changing_roles_or_session_version(self):
        before = dict(self.sql(
            "SELECT role,roles_json,session_version FROM user_accounts WHERE username=?",
            ('teacher1',),
        )[0])
        response = self.client.patch(
            '/api/users/teacher1',
            json={
                'name': 'Teacher One',
                'empId': 'E001',
                'professionalTitle': '品管醫檢師',
                'responsibilityTags': ['品管', '臨床教師', 'POCT'],
            },
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        user = response.get_json()['user']
        self.assertEqual(user['professionalTitle'], '品管醫檢師')
        self.assertEqual(user['responsibilityTags'], ['品管', '臨床教師', 'POCT'])
        self.assertEqual(user['role'], 'clinical_teacher')
        self.assertEqual(user['roles'], ['clinical_teacher', 'group_leader'])
        after = dict(self.sql(
            "SELECT role,roles_json,session_version,professional_title,responsibility_tags FROM user_accounts WHERE username=?",
            ('teacher1',),
        )[0])
        self.assertEqual(after['role'], before['role'])
        self.assertEqual(json.loads(after['roles_json']), json.loads(before['roles_json']))
        self.assertEqual(after['session_version'], before['session_version'])
        self.assertEqual(after['professional_title'], '品管醫檢師')
        self.assertEqual(json.loads(after['responsibility_tags']), ['品管', '臨床教師', 'POCT'])


if __name__ == '__main__':
    unittest.main()
