from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CiPolicyFailClosedTests(unittest.TestCase):
    def test_release_policy_uses_explicit_fail_closed_helpers(self):
        source = ROOT.joinpath('.github/workflows/phase3-pgy-checks.yml').read_text(encoding='utf-8')
        self.assertNotIn('! grep -q', source)
        self.assertIn('forbid_match()', source)
        self.assertIn('require_match()', source)
        self.assertIn("forbid_match '(dockerCommand|startCommand|command):.*material_worker\\.py' render.yaml", source)
        self.assertIn("require_match 'dockerCommand:[[:space:]]*python -u ai_question_worker\\.py' render.yaml", source)

    def test_postgres_service_and_real_integration_step_remain_enabled(self):
        source = ROOT.joinpath('.github/workflows/phase3-pgy-checks.yml').read_text(encoding='utf-8')
        self.assertIn('image: postgres:16', source)
        self.assertIn("TEACHER_POSTGRES_CI: '1'", source)
        self.assertIn('tests.test_postgres_integration_ci', source)


if __name__ == '__main__':
    unittest.main()
