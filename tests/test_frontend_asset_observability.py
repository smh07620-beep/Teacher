from __future__ import annotations

import unittest
from unittest.mock import patch

from flask import Flask

from teacher_app.frontend import assets


class FrontendAssetObservabilityTests(unittest.TestCase):
    def test_asset_injection_failure_preserves_response_and_is_logged(self):
        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY="asset-observability-test")

        @app.get("/system")
        def system_page():
            return "<html><body>original-system</body></html>"

        assets.register_pgy_frontend(app)
        with patch.object(assets, "_apply_asset_manifest", side_effect=RuntimeError("synthetic asset failure")):
            with self.assertLogs("teacher_app.frontend.assets", level="ERROR") as captured:
                response = app.test_client().get("/system")

        self.assertEqual(response.status_code, 200)
        self.assertIn("original-system", response.get_data(as_text=True))
        joined = "\n".join(captured.output)
        self.assertIn("Teacher frontend asset injection failed path=/system", joined)
        self.assertIn("synthetic asset failure", joined)


if __name__ == "__main__":
    unittest.main()
