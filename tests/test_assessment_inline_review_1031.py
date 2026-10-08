import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


class AssessmentInlineReviewTests(unittest.TestCase):
    def setUp(self):
        self.js = read("static/teacher-assessment-inline-1031.js")

    def test_module_is_loaded_after_action_queue(self):
        assets = read("teacher_app/frontend/assets.py")
        self.assertLess(assets.index("/teacher-action-queue-1024.js"), assets.index("/teacher-assessment-inline-1031.js"))

    def test_no_popups_or_inline_handlers(self):
        for banned in ("alert(", "confirm(", "prompt(", "data-csp-click", "onclick="):
            self.assertNotIn(banned, self.js)

    def test_server_remains_the_authority(self):
        # Only the existing scoped endpoints are used; reviewer identity is never sent from the browser.
        self.assertIn("fetch('/api/records'", self.js)
        self.assertIn("/review`", self.js)
        self.assertIn("method: 'PATCH'", self.js)
        self.assertNotIn("reviewerName:", self.js)

    def test_navigation_controls_exist(self):
        for marker in ("← 返回名單", "← 上一位", "下一位 →", "data-assess-save", "data-assess-step"):
            self.assertIn(marker, self.js)

    def test_tabs_open_inline_with_legacy_fallback(self):
        ws = read("static/teacher-workspace-1014.js")
        self.assertIn("window.TeacherAssessmentInline1031", ws)
        self.assertIn("await inline.show(tab)", ws)
        self.assertIn("await openReview()", ws)  # fallback kept
        queue = read("static/teacher-action-queue-1024.js")
        self.assertIn("inline.openRecord(", queue)

    def test_css_swaps_panes_inside_the_page(self):
        css = read("static/teacher-workspace-1014.css")
        self.assertIn('[data-assess-tab="pending"]', css)
        self.assertIn('[data-assess-tab="history"]', css)


if __name__ == "__main__":
    unittest.main()
