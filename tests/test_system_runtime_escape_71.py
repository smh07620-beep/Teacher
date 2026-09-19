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

    def test_runtime_frontend_rewrites_local_asset_versions_by_build(self):
        frontend = self.source("teacher_app/frontend/assets.py")
        self.assertIn("def _rewrite_local_asset_versions", frontend)
        self.assertIn("ASSET_VERSION", frontend)
        self.assertIn("RENDER_GIT_COMMIT", frontend)

    def test_retired_escape_guard_is_absent_and_api_client_follows_shared_core(self):
        frontend = self.source("teacher_app/frontend/assets.py")
        self.assertFalse((ROOT / "static" / "runtime-escape-guard-7111.js").exists())
        self.assertNotIn("/runtime-escape-guard-7111.js", frontend)
        self.assertIn('"/shared-core.js",', frontend)
        self.assertIn('"/api-client.js",', frontend)


if __name__ == "__main__":
    unittest.main()
