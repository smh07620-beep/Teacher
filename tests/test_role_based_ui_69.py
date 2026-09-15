import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class RoleBasedWorkspace69Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROOT.joinpath('static', 'rbac-ui-681.js').read_text(encoding='utf-8')

    def test_students_do_not_get_management_entry(self):
        self.assertIn("if (!workspaceAccess)", self.source)
        self.assertIn("document.querySelectorAll('.v575-manage-direct')", self.source)
        self.assertIn("entry.classList.add('hidden')", self.source)
        self.assertIn("entry.disabled = true", self.source)

    def test_workspace_navigation_is_permission_driven(self):
        expected = {
            "'course-materials': ['course.manage','material.manage']",
            "assessment: ['question.manage','exam.manage']",
            "teacher: ['evaluation.submit','evaluation.review','teacher.assessment.sign','evaluation.finalize']",
            "results: ['result.group.read']",
            "word: ['template.manage']",
            "people: ['user.manage']",
            "system: ['system.manage']",
        }
        for marker in expected:
            self.assertIn(marker, self.source)
        self.assertIn("if (!canOpenWorkspace(name))", self.source)

    def test_group_scoped_roles_are_locked_to_preferred_group(self):
        self.assertIn("roles.has('clinical_teacher') || roles.has('group_leader')", self.source)
        self.assertIn("!crossGroup", self.source)
        self.assertIn("select.innerHTML = `<option", self.source)
        self.assertIn("select.disabled = true", self.source)
        self.assertIn("user.preferredGroup", self.source)
        self.assertIn("education.cross_group.manage", self.source)

    def test_system_only_navigation_stays_hidden_from_teachers(self):
        self.assertIn("'admin-nav-word': WORKSPACE_RULES.word", self.source)
        self.assertIn("'admin-nav-people': WORKSPACE_RULES.people", self.source)
        self.assertIn("'admin-nav-system': WORKSPACE_RULES.system", self.source)
        self.assertIn("button.classList.toggle('hidden', !allowed)", self.source)

    def test_material_session_expiry_no_longer_mentions_admin_key(self):
        self.assertIn("登入已逾時，請重新登入", self.source)
        self.assertIn("沒有教材管理權限", self.source)
        self.assertIn("'X-Admin-Key': 'rbac-session'", self.source)
        self.assertNotIn("管理者金鑰錯誤", self.source)
        self.assertNotIn("sessionStorage.removeItem('admin_key'", self.source)

    def test_publish_and_review_actions_follow_capabilities(self):
        self.assertIn("if (!has('exam.publish'))", self.source)
        self.assertIn("if (!has('question.review'))", self.source)
        self.assertIn("MutationObserver", self.source)


if __name__ == '__main__':
    unittest.main()
