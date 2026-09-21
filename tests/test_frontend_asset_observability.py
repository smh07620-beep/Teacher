import unittest
from unittest.mock import patch

from flask import Flask

from teacher_app.frontend import assets


class FrontendAssetObservabilityTests(unittest.TestCase):
    def _app(self):
        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY="asset-test")

        @app.get("/")
        def home():
            return "<html><body><main>home</main></body></html>"

        @app.get("/system")
        def system_page():
            return "<html><body><script defer src=\"/shared-core.js\"></script><script defer src=\"/system-admin.js\"></script></body></html>"

        assets.register_pgy_frontend(app)
        return app

    def test_asset_injection_failure_is_logged_and_original_response_survives(self):
        app = self._app()
        with patch.object(assets, "_apply_asset_manifest", side_effect=RuntimeError("synthetic injection failure")):
            with self.assertLogs("teacher_app.frontend.assets", level="ERROR") as captured:
                response = app.test_client().get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("<main>home</main>", response.get_data(as_text=True))
        joined = "\n".join(captured.output)
        self.assertIn("frontend asset injection failed", joined)
        self.assertIn("path=/", joined)

    def test_successful_injection_remains_versioned(self):
        app = self._app()
        with patch.dict("os.environ", {"ASSET_VERSION": "ci-build-123"}, clear=False):
            response = app.test_client().get("/")
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("/portal-navigation-73.js?v=ci-build-123", body)
        self.assertIn("/home-profile-title-71.js?v=ci-build-123", body)


if __name__ == "__main__":
    unittest.main()
