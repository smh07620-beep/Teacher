import unittest

from flask import Flask, redirect

from teacher_app.frontend.cache_policy import register_browser_cache_policy


class ProtectedMediaCachePolicyTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)

        @app.get("/uploaded-slides/<folder>/<path:filename>")
        def slide(folder, filename):
            return b"png", 200, {"Content-Type": "image/png"}

        @app.get("/material-preview/<material_id>/page/<int:page_no>.png")
        def page(material_id, page_no):
            return b"png", 200, {"Content-Type": "image/png", "Cache-Control": "private, max-age=300"}

        @app.get("/material-preview/<material_id>")
        def missing(material_id):
            return b"nope", 404

        @app.get("/view/<material_id>")
        def signed(material_id):
            return redirect("https://storage.example/signed", code=302)

        @app.get("/static-art.png")
        def art():
            return b"png", 200, {"Content-Type": "image/png"}

        @app.get("/app.js")
        def script():
            return b"1", 200, {"Content-Type": "text/javascript"}

        @app.get("/api/me")
        def api():
            return {}, 200

        register_browser_cache_policy(app)
        self.client = app.test_client()

    def test_login_protected_page_images_are_private_and_short_lived(self):
        for url in ("/uploaded-slides/m1/slide-01.png", "/material-preview/m1/page/2.png"):
            value = self.client.get(url).headers["Cache-Control"]
            self.assertIn("private", value, url)
            self.assertNotIn("public", value, url)
            self.assertIn("max-age=300", value, url)
            self.assertNotIn("86400", value, url)

    def test_errors_and_signed_redirects_are_not_cached(self):
        self.assertEqual(self.client.get("/material-preview/m1").headers["Cache-Control"], "no-store")
        self.assertEqual(self.client.get("/view/m1").headers["Cache-Control"], "no-store")

    def test_versioned_static_assets_and_api_policy_is_unchanged(self):
        self.assertEqual("no-cache", self.client.get("/app.js").headers["Cache-Control"])
        self.assertIn("max-age=86400", self.client.get("/static-art.png").headers["Cache-Control"])
        self.assertEqual(self.client.get("/api/me").headers["Cache-Control"], "no-store")


if __name__ == "__main__":
    unittest.main()
