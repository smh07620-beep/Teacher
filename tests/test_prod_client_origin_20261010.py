"""Regression: the production monitoring client must send Origin/Referer on POST.

The site's CSRF origin check answers HTTP 403 to a state-changing /api/ request
that carries neither header.  The monitoring client used to send neither, and
mapped that 403 to "帳號或密碼不正確", so a correct monitoring account looked
like a wrong password in the GitHub workflow.
"""
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from prod_client import ApiError, ProductionClient  # noqa: E402


class _SiteStub(BaseHTTPRequestHandler):
    seen: list[dict] = []

    def log_message(self, *args):  # silence test output
        pass

    def _reply(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        data = json.loads(self.rfile.read(length) or b"{}")
        origin = self.headers.get("Origin", "")
        referer = self.headers.get("Referer", "")
        type(self).seen.append({"origin": origin, "referer": referer})
        host = self.headers.get("Host", "")
        # Same rule as teacher_app.common.security.csrf_origin_ok().
        candidate = origin or referer
        if not candidate or candidate.split("://", 1)[-1].split("/", 1)[0] != host:
            return self._reply(403, {"error": "安全驗證失敗：請從本站頁面重新操作。"})
        if self.path == "/api/auth/login":
            if data.get("password") == "good":
                return self._reply(200, {"ok": True, "user": {"username": data.get("username")}})
            return self._reply(401, {"error": "帳號或密碼不正確，請洽管理者。"})
        if self.path == "/api/rate-limited":
            return self._reply(429, {"error": "登入失敗次數過多"})
        return self._reply(404, {})


class ProductionClientOriginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _SiteStub.seen = []
        cls.server = HTTPServer(("127.0.0.1", 0), _SiteStub)
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def test_correct_credentials_log_in(self):
        user = ProductionClient(self.base).login("monitor", "good")
        self.assertEqual(user.get("username"), "monitor")
        self.assertEqual(_SiteStub.seen[-1]["origin"], self.base)
        self.assertTrue(_SiteStub.seen[-1]["referer"].startswith(self.base))

    def test_wrong_password_is_reported_as_wrong_password(self):
        with self.assertRaises(ApiError) as ctx:
            ProductionClient(self.base).login("monitor", "bad")
        self.assertEqual(ctx.exception.status, 401)
        self.assertIn("帳號或密碼不正確", str(ctx.exception))

    def test_csrf_rejection_is_not_blamed_on_the_password(self):
        client = ProductionClient(self.base)
        status, _headers, _body = client.request(
            "POST", "/api/auth/login", json_body={"username": "m", "password": "good"}, headers={"Origin": "", "Referer": ""}
        )
        self.assertEqual(status, 403)

    def test_get_requests_do_not_get_origin_headers(self):
        client = ProductionClient(self.base)
        # GET to the stub is unsupported (501); only the absence of the header matters here.
        captured = {}
        original = client._opener.open

        def spy(request, timeout=None):
            captured["origin"] = request.get_header("Origin")
            return original(request, timeout=timeout)

        client._opener.open = spy
        try:
            client.request("GET", "/health")
        except Exception:
            pass
        self.assertIsNone(captured.get("origin"))


if __name__ == "__main__":
    unittest.main()
