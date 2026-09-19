from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RcFinalValidationGateTests(unittest.TestCase):
    def test_release_checks_run_on_current_rc_branch_push(self):
        workflow = ROOT.joinpath('.github', 'workflows', 'phase3-pgy-checks.yml').read_text(encoding='utf-8')
        self.assertIn('feature/teacher-content-authoring-studio-72', workflow)

    def test_rc_matrix_requires_exact_commit_release_checks(self):
        matrix = ROOT.joinpath('RC_FEATURE_UI_COVERAGE_MATRIX.md').read_text(encoding='utf-8')
        self.assertIn('Teacher release checks', matrix)
        self.assertIn('exact RC commit', matrix)


if __name__ == '__main__':
    unittest.main()
