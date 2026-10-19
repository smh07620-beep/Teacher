"""2026-10-17: single learning path and desktop reader chrome."""
import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "static"


class SingleLearningPathTests(unittest.TestCase):
    def test_no_separate_exam_switch_for_learners(self):
        html = (STATIC / "system.html").read_text(encoding="utf-8")
        self.assertNotIn('id="module-btn-exam"', html)
        nav = html[html.index('class="v56-system-mobile-nav"'):]
        nav = nav[: nav.index("</nav>")]
        self.assertNotIn("switchLearningModule('exam')", nav)

    def test_reader_measured_materials_have_no_manual_complete(self):
        js = (STATIC / "system-learner.js").read_text(encoding="utf-8")
        self.assertIn("function materialAutoTracked(m)", js)
        self.assertIn("(s.isBuiltin || materialAutoTracked(s))", js)

    def test_desktop_reader_idle_chrome(self):
        js = (STATIC / "system-learner.js").read_text(encoding="utf-8")
        css = (STATIC / "learner.css").read_text(encoding="utf-8")
        self.assertIn("bindReaderIdleChrome", js)
        self.assertIn("(pointer:fine)", js)
        self.assertIn(".reader-idle #slide-prev-btn", css)
        self.assertIn("#slide-viewer-shell:fullscreen.reader-idle #reader-head", css)


if __name__ == "__main__":
    unittest.main()
