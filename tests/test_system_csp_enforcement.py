import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from teacher_app.common.security import register_production_hardening
from teacher_app.frontend.assets import ASSET_MANIFEST


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
INLINE_HANDLER = re.compile(
    r"\son[a-z][a-z0-9_-]*\s*=",
    re.IGNORECASE,
)
INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc\s*=)[^>]*>", re.IGNORECASE)


class SystemCspEnforcementTests(unittest.TestCase):
    def test_canonical_system_surfaces_have_no_inline_event_attributes(self):
        chosen = (
            "system.html",
            "admin-announcements.js",
            "admin-ai-questions.js",
            "admin-course-material.js",
            "admin-doc-templates.js",
            "admin-jobs.js",
            "admin-materials.js",
            "admin-people.js",
            "admin-pgy-assessments.js",
            "admin-question-bank.js",
            "admin-question-editor-ui.js",
            "admin-results-data.js",
            "atlas-70.js",
            "course-wizard-681.js",
            "system-exam.js",
            "system-learner.js",
            "teaching.js",
        )
        for name in chosen:
            with self.subTest(name=name):
                source = (STATIC / name).read_text(encoding="utf-8")
                self.assertIsNone(INLINE_HANDLER.search(source))

    def test_all_live_html_surfaces_have_no_inline_script_execution(self):
        for name in ("index.html", "area-internal.html", "area-pgy.html", "login.html", "system.html"):
            with self.subTest(name=name):
                source = (STATIC / name).read_text(encoding="utf-8")
                self.assertIsNone(INLINE_HANDLER.search(source))
                self.assertIsNone(INLINE_SCRIPT.search(source))

    def test_portal_behaviors_removed_from_html_are_owned_by_portal_runtime(self):
        index = (STATIC / "index.html").read_text(encoding="utf-8")
        pgy = (STATIC / "area-pgy.html").read_text(encoding="utf-8")
        runtime = (STATIC / "portal-v56.js").read_text(encoding="utf-8")

        self.assertIn('id="v561-progress-open"', index)
        self.assertIn("progressOpen?.addEventListener('click',open)", runtime)
        self.assertIn("data-pgy-management-only", pgy)
        self.assertIn("function syncPgyManagementVisibility()", runtime)
        self.assertIn("syncPgyManagementVisibility();", runtime)

    def test_csp_delegate_is_canonical_and_does_not_eval_action_text(self):
        source = (STATIC / "system-csp-actions.js").read_text(encoding="utf-8")
        self.assertIn("data-csp-click", source)
        self.assertIn("MutationObserver", source)
        self.assertIn("ALLOWED_ACTIONS", source)
        self.assertIn("statement === 'event.preventDefault()'", source)
        self.assertIn("statement === 'event.stopPropagation()'", source)
        self.assertIn("event.target.closest(`[${attribute}]`)", source)
        self.assertNotIn("eval(", source)
        self.assertNotIn("new Function", source)
        self.assertIn("/system-csp-actions.js", ASSET_MANIFEST["system"]["body"])

    def test_question_delete_discovery_uses_csp_action_attributes(self):
        source = (STATIC / "admin-question-bank.js").read_text(encoding="utf-8")
        self.assertNotIn('button[onclick*=', source)
        for action in (
            "adminDeleteQuizQuestion",
            "adminBulkDeleteQuestions",
            "adminDeleteQuizCategory",
        ):
            self.assertIn(f'button[data-csp-click*="{action}"]', source)

    def test_csp_enforce_header_disallows_inline_script_handlers_globally(self):
        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY="test")

        @app.get("/")
        def portal_page():
            return "ok"

        @app.get("/system")
        def system_page():
            return "ok"

        with patch.dict(os.environ, {"CSP_ENFORCE": "true"}, clear=False):
            register_production_hardening(app, current_user=lambda: None)
            client = app.test_client()
            responses = (client.get("/"), client.get("/system"))

        for response in responses:
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("Content-Security-Policy-Report-Only", response.headers)
            csp = response.headers["Content-Security-Policy"]
            directives = {part.strip().split(" ", 1)[0]: part.strip() for part in csp.split(";") if part.strip()}
            self.assertIn("script-src", directives)
            self.assertNotIn("'unsafe-inline'", directives["script-src"])
            self.assertEqual(directives.get("script-src-attr"), "script-src-attr 'none'")
            self.assertEqual(
                directives.get("frame-src"),
                "frame-src 'self' https://www.youtube-nocookie.com https://player.vimeo.com",
            )


if __name__ == "__main__":
    unittest.main()
