from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SystemRuntimeEscape71Tests(unittest.TestCase):
    def source(self, path: str) -> str:
        return (ROOT / path).read_text(encoding="utf-8")

    def test_shared_core_exports_legacy_escape_helper(self):
        source = self.source("static/shared-core.js")
        self.assertIn("global.escapeHtml = escapeHtml;", source)
        self.assertIn("escapeHtml,", source)

    def test_shared_core_loads_before_course_and_exam_renderers(self):
        html = self.source("static/system.html")
        shared = html.index('/shared-core.js')
        exam = html.index('/system-exam.js')
        teaching = html.index('/teaching.js')
        self.assertLess(shared, exam)
        self.assertLess(shared, teaching)

    def test_course_and_exam_renderers_have_escape_dependency_covered(self):
        teaching = self.source("static/teaching.js")
        exam = self.source("static/system-exam.js")
        self.assertIn("escapeHtml(", teaching)
        self.assertIn("escapeHtml(", exam)

    def test_runtime_frontend_forces_fresh_critical_asset_versions(self):
        frontend = self.source("pgy_frontend.py")
        self.assertIn('/shared-core.js?v=7111', frontend)
        self.assertIn('/system-exam.js?v=7111', frontend)
        self.assertIn('/teaching.js?v=7111', frontend)
        self.assertIn('/runtime-escape-guard-7111.js?v=7111', frontend)

    def test_runtime_escape_guard_has_independent_fallback(self):
        guard = self.source("static/runtime-escape-guard-7111.js")
        self.assertIn("typeof global.escapeHtml === 'function'", guard)
        self.assertIn("global.AppCore", guard)
        self.assertIn("global.escapeHtml = canonical || function", guard)
        self.assertIn("__teacherEscapeGuard7111", guard)

    def test_escape_guard_is_injected_immediately_after_fresh_shared_core(self):
        frontend = self.source("pgy_frontend.py")
        shared = frontend.index('fresh_shared_core =')
        guard = frontend.index('escape_guard =')
        injection = frontend.index('fresh_shared_core + "\\n" + escape_guard')
        self.assertLess(shared, guard)
        self.assertLess(guard, injection)


if __name__ == "__main__":
    unittest.main()
