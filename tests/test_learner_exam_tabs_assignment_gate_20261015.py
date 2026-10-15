"""The learner exam list must ask for the assigned-only view (2026-10-15).

Without ?view=learner a group leader / teacher got every course and exam of the group,
so unassigned courses showed up in the learner reading area. Teacher/admin pages
(admin=1 or a persona) keep the full list.
"""
import unittest
from pathlib import Path

SRC = (Path(__file__).resolve().parents[1] / "static" / "system-exam.js").read_text(encoding="utf-8")


class LearnerExamTabsGateTests(unittest.TestCase):
    def test_exam_tabs_request_learner_view_only_outside_admin_pages(self):
        helper = SRC[SRC.index("function learnerViewQuery"):SRC.index("async function renderDynamicExamTabs")]
        self.assertIn("get('admin')==='1'", helper)
        self.assertIn("get('persona')", helper)
        self.assertIn("&view=learner", helper)
        body = SRC[SRC.index("async function renderDynamicExamTabs"):][:1200]
        self.assertEqual(body.count("${learnerViewQuery()}"), 2)


if __name__ == "__main__":
    unittest.main()
