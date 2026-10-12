"""Assessment tabs must read data-assessment-tab-1030 via getAttribute.

``dataset`` camel-cases only dash+letter, so ``data-assessment-tab-1030`` is
``dataset['assessmentTab-1030']`` and ``dataset.assessmentTab1030`` is always
undefined, which made every tab button a silent no-op.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class AssessmentTabAttributeTests(unittest.TestCase):
    def test_no_dataset_access_for_digit_suffixed_tab_attribute(self):
        for name in ("teacher-workspace-1014.js", "teacher-assessment-inline-1031.js"):
            source = (ROOT / "static" / name).read_text(encoding="utf-8")
            self.assertNotIn("dataset.assessmentTab1030", source, name)
            self.assertIn("getAttribute('data-assessment-tab-1030')", source, name)


if __name__ == "__main__":
    unittest.main()


class HistoryResultsLinkAndPillTest(unittest.TestCase):
    def test_history_has_results_workspace_button(self):
        src = (ROOT / "static/teacher-assessment-inline-1031.js").read_text(encoding="utf-8")
        self.assertIn("data-assess-results-workspace", src)
        self.assertIn("AppWorkspaceRoutes.open('results')", src)

    def test_return_pill_not_in_teacher_persona(self):
        src = (ROOT / "static/learner-study-exam-loop-1032.js").read_text(encoding="utf-8")
        self.assertIn("persona=teacher", src)
        self.assertIn("getClientRects().length > 0", src)
