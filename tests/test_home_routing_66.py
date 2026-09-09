import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class HomeRouting66Tests(
    unittest.TestCase
):
    def source(self, rel):
        return ROOT.joinpath(
            rel
        ).read_text(
            encoding="utf-8"
        )

    def test_pending_exam_links_preserve_area_group_and_exam_id(self):
        index = self.source(
            "static/index.html"
        )

        portal = self.source(
            "static/portal-v56.js"
        )

        self.assertIn(
            'id="v66-pending-all"',
            index,
        )

        self.assertNotIn(
            '<a href="/pgy">查看待考 →</a>',
            index,
        )

        self.assertIn(
            "module:'exam'",
            portal,
        )

        self.assertIn(
            "qs.set('examId',examId)",
            portal,
        )

        self.assertIn(
            "x.id||x.examId||x.quizId",
            portal,
        )

    def test_exam_page_auto_opens_requested_exam(self):
        source = self.source(
            "static/system-exam.js"
        )

        self.assertIn(
            "get('examId')",
            source,
        )

        self.assertIn(
            "requestedCategory",
            source,
        )

        self.assertIn(
            "initialCategory",
            source,
        )

        self.assertIn(
            "switchDynamicCategory",
            source,
        )

        system_html = self.source(
            "static/system.html"
        )

        self.assertIn(
            "system-exam.js?v=6602",
            system_html,
        )

    def test_home_uses_short_ttl_cache_and_inflight_deduplication(self):
        source = self.source(
            "static/portal-v56.js"
        )

        for marker in (
            "HOME_CACHE_TTL",
            "HOME_PERSONAL_TTL",
            "HOME_SLIDES_TTL",
            "homeMemoryCache",
            "homeInflight",
            "fetchJSONCached",
            "sessionStorage.setItem",
            "homeInflight.has(url)",
            "clearHomeCache",
        ):
            self.assertIn(
                marker,
                source,
            )

        index = self.source(
            "static/index.html"
        )

        self.assertIn(
            "portal-v56.js?v=6602",
            index,
        )


if __name__ == "__main__":
    unittest.main()
