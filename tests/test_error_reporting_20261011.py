from pathlib import Path
import importlib.util
import json
import sys
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from teacher_app.maintenance import error_reporting  # noqa: E402

HAS_SENTRY = importlib.util.find_spec("sentry_sdk") is not None
FAKE_DSN = "https://publickey@o0.ingest.sentry.io/1"


class ScrubEventTests(unittest.TestCase):
    def test_removes_request_content_user_and_breadcrumbs(self):
        event = {
            "request": {
                "url": "https://teacher.example/api/exams/7?token=abc123#frag",
                "method": "POST",
                "cookies": {"session": "s3cret"},
                "headers": {"Authorization": "Bearer x", "Cookie": "session=s3cret"},
                "data": {"password": "hunter2"},
                "query_string": "token=abc123",
                "env": {"REMOTE_ADDR": "10.0.0.5"},
            },
            "user": {"id": "42", "ip_address": "10.0.0.5"},
            "breadcrumbs": {"values": [{"message": "x"}]},
            "server_name": "render-instance",
            "exception": {"values": [{"type": "RuntimeError"}]},
        }
        result = error_reporting.scrub_event(event)
        self.assertEqual(result["request"], {"url": "https://teacher.example/api/exams/7", "method": "POST"})
        for key in ("user", "breadcrumbs", "server_name"):
            self.assertNotIn(key, result)
        self.assertEqual(result["exception"]["values"][0]["type"], "RuntimeError")

    def test_event_without_request_is_left_alone(self):
        self.assertEqual(error_reporting.scrub_event({"message": "boom"}), {"message": "boom"})


class InitBehaviourTests(unittest.TestCase):
    def test_without_dsn_nothing_is_initialised(self):
        fake = types.ModuleType("sentry_sdk")
        fake.init = mock.Mock()
        with mock.patch.dict(sys.modules, {"sentry_sdk": fake}):
            self.assertFalse(error_reporting.init_error_reporting({}))
            self.assertFalse(error_reporting.init_error_reporting({"SENTRY_DSN": "   "}))
        fake.init.assert_not_called()

    def test_missing_sdk_does_not_break_startup(self):
        with mock.patch.dict(sys.modules, {"sentry_sdk": None}):
            self.assertFalse(error_reporting.init_error_reporting({"SENTRY_DSN": FAKE_DSN}))

    def test_sample_rate_is_clamped_and_tolerant(self):
        self.assertEqual(error_reporting._sample_rate("0.25"), 0.25)
        self.assertEqual(error_reporting._sample_rate("5"), 1.0)
        self.assertEqual(error_reporting._sample_rate("-1"), 0.0)
        self.assertEqual(error_reporting._sample_rate("abc"), 1.0)


@unittest.skipUnless(HAS_SENTRY, "sentry-sdk is not installed")
class RealSdkTests(unittest.TestCase):
    def setUp(self):
        import sentry_sdk
        from sentry_sdk.transport import Transport

        class CaptureTransport(Transport):
            def __init__(self, options=None):
                super().__init__(options)
                self.events = []

            def capture_envelope(self, envelope):
                for item in envelope.items:
                    if item.type == "event":
                        self.events.append(item.payload.json)

        self.sentry_sdk = sentry_sdk
        self.transport = CaptureTransport()

    def tearDown(self):
        self.sentry_sdk.init()  # no DSN: disables the client again

    def _app(self):
        from flask import Flask

        app = Flask(__name__)

        @app.post("/api/boom")
        def boom():
            raise RuntimeError("exam export failed")

        return app

    def test_unhandled_error_is_reported_without_personal_data(self):
        env = {"SENTRY_DSN": FAKE_DSN, "SENTRY_ENVIRONMENT": "staging"}
        with self.assertLogs(error_reporting.logger, level="WARNING") as logs:
            self.assertTrue(error_reporting.init_error_reporting(env, transport=self.transport))
        # 啟用訊息必須在預設記錄等級下看得到，管理者才能在 Render 記錄確認。
        self.assertTrue(any("sentry_enabled release=teacher@" in line for line in logs.output))
        app = self._app()
        client = app.test_client()
        client.set_cookie("session", "s3cret-cookie")
        response = client.post(
            "/api/boom?token=query-secret",
            json={"password": "hunter2", "answer": "patient answer text"},
            headers={"Authorization": "Bearer header-secret"},
        )
        self.assertEqual(response.status_code, 500)
        self.sentry_sdk.flush()

        self.assertEqual(len(self.transport.events), 1)
        event = self.transport.events[0]
        self.assertEqual(event["exception"]["values"][0]["type"], "RuntimeError")
        self.assertEqual(event["environment"], "staging")
        self.assertTrue(event["release"].startswith("teacher@"))
        self.assertEqual(event["request"]["url"].split("?")[0], event["request"]["url"])
        self.assertTrue(event["request"]["url"].endswith("/api/boom"))
        self.assertNotIn("user", event)

        serialized = json.dumps(event, ensure_ascii=False)
        for secret in ("s3cret-cookie", "query-secret", "hunter2", "header-secret", "patient answer text"):
            self.assertNotIn(secret, serialized)

    def test_test_event_tool_sends_one_scrubbed_message(self):
        spec = importlib.util.spec_from_file_location("sentry_test_event_under_test", ROOT / "tools" / "sentry_test_event.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(module.send_test_event({"SENTRY_DSN": FAKE_DSN}, transport=self.transport))
        self.assertEqual(len(self.transport.events), 1)
        event = self.transport.events[0]
        self.assertIn("Teacher 錯誤通知測試", json.dumps(event, ensure_ascii=False))
        self.assertNotIn("user", event)
        self.assertFalse(module.send_test_event({}))

    def test_invalid_dsn_is_swallowed(self):
        self.assertFalse(error_reporting.init_error_reporting({"SENTRY_DSN": "not-a-dsn"}))


if __name__ == "__main__":
    unittest.main()
