import gzip
import tempfile
import unittest
from pathlib import Path

from flask import Flask, jsonify, send_file, Response

from teacher_app.frontend.compression import register_response_compression

BIG_TEXT = "教材內容 abc " * 400


def build_app(static_file: Path | None = None) -> Flask:
    app = Flask(__name__)

    @app.get("/json")
    def json_route():
        return jsonify({"items": [BIG_TEXT] * 3})

    @app.get("/small")
    def small_route():
        return jsonify({"ok": True})

    @app.get("/html")
    def html_route():
        return Response(f"<html><body>{BIG_TEXT}</body></html>", mimetype="text/html")

    @app.get("/image")
    def image_route():
        return Response(b"\x00" * 5000, mimetype="image/webp")

    @app.get("/stream")
    def stream_route():
        return Response((BIG_TEXT for _ in range(3)), mimetype="text/plain")

    @app.get("/partial")
    def partial_route():
        return Response(BIG_TEXT, status=206, mimetype="text/plain")

    @app.get("/already")
    def already_route():
        response = Response(gzip.compress(BIG_TEXT.encode()), mimetype="text/plain")
        response.headers["Content-Encoding"] = "gzip"
        return response

    if static_file is not None:
        @app.get("/file.js")
        def file_route():
            return send_file(static_file, mimetype="application/javascript")

    return register_response_compression(app)


class ResponseCompressionTests(unittest.TestCase):
    def test_json_is_gzipped_and_roundtrips(self):
        client = build_app().test_client()
        plain = client.get("/json", headers={"Accept-Encoding": "identity"})
        zipped = client.get("/json", headers={"Accept-Encoding": "gzip, deflate, br"})
        self.assertEqual(zipped.headers["Content-Encoding"], "gzip")
        self.assertIn("Accept-Encoding", zipped.headers["Vary"])
        self.assertEqual(int(zipped.headers["Content-Length"]), len(zipped.data))
        self.assertLess(len(zipped.data), len(plain.data) / 4)
        self.assertEqual(gzip.decompress(zipped.data), plain.data)

    def test_html_is_gzipped(self):
        response = build_app().test_client().get("/html", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(response.headers["Content-Encoding"], "gzip")
        self.assertIn("教材內容", gzip.decompress(response.data).decode("utf-8"))

    def test_client_without_gzip_gets_plain_but_vary_is_set(self):
        client = build_app().test_client()
        for header in ({}, {"Accept-Encoding": "identity"}, {"Accept-Encoding": "gzip;q=0"}):
            response = client.get("/json", headers=header)
            self.assertNotIn("Content-Encoding", response.headers, header)
            self.assertIn("Accept-Encoding", response.headers["Vary"], header)

    def test_small_responses_are_left_alone(self):
        response = build_app().test_client().get("/small", headers={"Accept-Encoding": "gzip"})
        self.assertNotIn("Content-Encoding", response.headers)

    def test_media_and_binary_are_never_compressed(self):
        response = build_app().test_client().get("/image", headers={"Accept-Encoding": "gzip"})
        self.assertNotIn("Content-Encoding", response.headers)
        self.assertEqual(len(response.data), 5000)

    def test_streams_partial_and_already_encoded_are_untouched(self):
        client = build_app().test_client()
        headers = {"Accept-Encoding": "gzip"}
        self.assertNotIn("Content-Encoding", client.get("/stream", headers=headers).headers)
        self.assertNotIn("Content-Encoding", client.get("/partial", headers=headers).headers)
        already = client.get("/already", headers=headers)
        self.assertEqual(already.headers["Content-Encoding"], "gzip")
        self.assertEqual(gzip.decompress(already.data).decode("utf-8"), BIG_TEXT)

    def test_head_and_errors_are_untouched(self):
        client = build_app().test_client()
        self.assertNotIn("Content-Encoding", client.head("/json", headers={"Accept-Encoding": "gzip"}).headers)
        self.assertNotIn("Content-Encoding", client.get("/missing", headers={"Accept-Encoding": "gzip"}).headers)

    def test_static_file_is_gzipped_and_served_from_cache_the_second_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.js"
            path.write_text("console.log('教材');\n" * 300, encoding="utf-8")
            client = build_app(path).test_client()
            headers = {"Accept-Encoding": "gzip"}
            first = client.get("/file.js", headers=headers)
            second = client.get("/file.js", headers=headers)
            for response in (first, second):
                self.assertEqual(response.headers["Content-Encoding"], "gzip")
                self.assertTrue(gzip.decompress(response.data).decode("utf-8").startswith("console.log"))
                self.assertTrue(response.headers["ETag"].startswith("W/"))
            self.assertEqual(first.data, second.data)
            plain = client.get("/file.js", headers={"Accept-Encoding": "identity"})
            self.assertNotIn("Content-Encoding", plain.headers)
            self.assertGreater(len(plain.data), len(first.data))
            plain.close()

    def test_switch_off_with_environment(self):
        import os
        old = os.environ.get("RESPONSE_COMPRESSION")
        os.environ["RESPONSE_COMPRESSION"] = "false"
        try:
            response = build_app().test_client().get("/json", headers={"Accept-Encoding": "gzip"})
            self.assertNotIn("Content-Encoding", response.headers)
        finally:
            if old is None:
                os.environ.pop("RESPONSE_COMPRESSION", None)
            else:
                os.environ["RESPONSE_COMPRESSION"] = old


if __name__ == "__main__":
    unittest.main()
