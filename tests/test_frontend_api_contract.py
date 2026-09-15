import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class FrontendApiContractTests(
    unittest.TestCase
):
    def source(self, path):
        return ROOT.joinpath(
            path
        ).read_text(
            encoding="utf-8"
        )

    def test_shared_core_has_structured_error_handling(self):
        source = self.source(
            "static/shared-core.js"
        )

        for marker in (
            "class AppApiError",
            "errorDetail",
            "retry-after",
            "x-request-id",
            "x-correlation-id",
            "loginRequired",
            "NETWORK_ERROR",
            "normalizeApiError",
        ):
            self.assertIn(
                marker,
                source,
            )

        for status in (
            "case 401:",
            "case 403:",
            "case 409:",
            "case 413:",
            "case 429:",
        ):
            self.assertIn(
                status,
                source,
            )

    def test_exam_frontend_uses_shared_api(self):
        source = self.source(
            "static/exam-integrity.js"
        )

        self.assertIn(
            "if(typeof C.api==='function')",
            source,
        )

        self.assertIn(
            "return C.api(path,options)",
            source,
        )

    def test_exam_frontend_does_not_expect_answer_key(self):
        source = self.source(
            "static/exam-integrity.js"
        )

        self.assertNotIn(
            "correct:q.correct",
            source,
        )

        self.assertNotIn(
            "explanation:q.explanation",
            source,
        )

    def test_maintenance_restore_uses_shared_api(self):
        source = self.source(
            "static/maintenance-64.js"
        )

        self.assertIn(
            "return C.api(path,options)",
            source,
        )

        self.assertIn(
            "'/api/maintenance/restore'",
            source,
        )

        self.assertNotIn(
            "fetch('/api/maintenance/restore'",
            source,
        )

    def test_pgy_prefers_shared_api(self):
        source = self.source(
            "static/pgy-workflow.js"
        )

        self.assertIn(
            "const api = C.api ||",
            source,
        )

        self.assertIn(
            "error.code = detail.code",
            source,
        )


if __name__ == "__main__":
    unittest.main()
