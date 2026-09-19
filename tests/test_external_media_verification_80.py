import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask, g

import release_contract
from teacher_app.config import external_media_hospital_cdn_hosts
from teacher_app.maintenance import migrations
from teacher_app.maintenance import external_media_verify as maintenance_verify
from teacher_app.materials import external_media
from teacher_app.materials.external_media_routes import register_external_media
from teacher_app.materials.external_media_verification import verify_media


class ExternalMediaCanonical80Tests(unittest.TestCase):
    def test_fixed_providers_and_explicit_hospital_cdn_allowlist(self):
        youtube = external_media.validate_external_url(
            "https://www.youtube.com/shorts/dQw4w9WgXcQ"
        )
        self.assertEqual(youtube["canonicalUrl"], "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertTrue(youtube["playbackUrl"].startswith("https://www.youtube-nocookie.com/embed/"))

        vimeo = external_media.validate_external_url("https://player.vimeo.com/video/123456")
        self.assertEqual(vimeo["provider"], "vimeo")
        self.assertEqual(vimeo["canonicalUrl"], "https://vimeo.com/123456")
        self.assertTrue(vimeo["playbackUrl"].startswith("https://player.vimeo.com/video/123456"))

        for refused in (
            "https://media.example.edu/lesson.mp4",
            "https://untrusted.example/lesson.webm",
            "http://cdn.hospital.example/lesson.mp4",
            "https://127.0.0.1/lesson.mp4",
            "https://localhost/lesson.mp4",
        ):
            with self.subTest(refused=refused), self.assertRaises(ValueError):
                external_media.validate_external_url(refused)

        cdn = external_media.validate_external_url(
            "https://cdn.hospital.example/lesson.mp4#ignored",
            ["cdn.hospital.example"],
        )
        self.assertEqual(cdn["provider"], "direct")
        self.assertEqual(cdn["canonicalUrl"], "https://cdn.hospital.example/lesson.mp4")
        self.assertEqual(cdn["providerMetadata"]["providerKind"], "hospital_cdn")
        with self.assertRaises(ValueError):
            external_media.validate_external_url(
                "https://cdn.hospital.example/lesson.html",
                ["cdn.hospital.example"],
            )

    def test_private_literal_requires_exact_explicit_cdn_configuration(self):
        configured = external_media.validate_external_url(
            "https://127.0.0.1/internal.mp4",
            ["127.0.0.1"],
        )
        self.assertEqual(configured["providerMetadata"]["cdnHost"], "127.0.0.1")

    def test_env_parser_has_no_wildcard_scheme_or_host_port(self):
        env = {
            "EXTERNAL_MEDIA_HOSPITAL_CDN_HOSTS": (
                "cdn1.hospital.example, CDN2.HOSPITAL.EXAMPLE;*.hospital.example "
                "https://bad.example cdn3.hospital.example:8443"
            )
        }
        self.assertEqual(
            external_media_hospital_cdn_hosts(env),
            ("cdn1.hospital.example", "cdn2.hospital.example"),
        )


class ExternalMediaVerifier80Tests(unittest.TestCase):
    def test_youtube_oembed_uses_fixed_endpoint_and_rejects_cross_host_redirect(self):
        calls = []

        def ok_request(method, url, **kwargs):
            calls.append((method, url, kwargs))
            return {
                "status": 200,
                "headers": {"content-type": "application/json"},
                "body": json.dumps({"title": "Lesson", "author_name": "Hospital"}).encode(),
            }

        result = verify_media(
            {
                "provider": "youtube",
                "canonicalUrl": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            },
            http_request=ok_request,
        )
        self.assertEqual(result["availabilityStatus"], "available")
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0][1].startswith("https://www.youtube.com/oembed?"))

        calls.clear()

        def redirect_request(method, url, **kwargs):
            calls.append(url)
            return {"status": 302, "headers": {"location": "https://evil.example/oembed"}, "body": b""}

        blocked = verify_media(
            {
                "provider": "youtube",
                "canonicalUrl": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            },
            http_request=redirect_request,
        )
        self.assertEqual(blocked["availabilityStatus"], "error")
        self.assertEqual(len(calls), 1)
        self.assertNotIn("evil.example", calls[0])

    def test_hospital_cdn_redirects_stay_inside_exact_allowlist_and_content_types(self):
        calls = []

        def allowed_request(method, url, **kwargs):
            calls.append((method, url, kwargs.get("headers", {})))
            if "cdn1" in url:
                return {"status": 302, "headers": {"location": "https://cdn2.hospital.example/final.mp4"}, "body": b""}
            return {"status": 200, "headers": {"content-type": "video/mp4"}, "body": b""}

        result = verify_media(
            {"provider": "direct", "canonicalUrl": "https://cdn1.hospital.example/start.mp4"},
            hospital_hosts={"cdn1.hospital.example", "cdn2.hospital.example"},
            http_request=allowed_request,
        )
        self.assertEqual(result["availabilityStatus"], "available")
        self.assertEqual([call[0] for call in calls], ["HEAD", "HEAD"])

        calls.clear()

        def blocked_request(method, url, **kwargs):
            calls.append(url)
            return {"status": 302, "headers": {"location": "https://evil.example/video.mp4"}, "body": b""}

        blocked = verify_media(
            {"provider": "direct", "canonicalUrl": "https://cdn1.hospital.example/start.mp4"},
            hospital_hosts={"cdn1.hospital.example"},
            http_request=blocked_request,
        )
        self.assertEqual(blocked["availabilityStatus"], "error")
        self.assertEqual(calls, ["https://cdn1.hospital.example/start.mp4"])

        wrong_type = verify_media(
            {"provider": "direct", "canonicalUrl": "https://cdn1.hospital.example/start.mp4"},
            hospital_hosts={"cdn1.hospital.example"},
            http_request=lambda *_args, **_kwargs: {
                "status": 200,
                "headers": {"content-type": "text/html"},
                "body": b"",
            },
        )
        self.assertEqual(wrong_type["availabilityStatus"], "unavailable")

    def test_cdn_head_fallback_get_is_bounded_and_uses_range(self):
        calls = []

        def request(method, url, **kwargs):
            calls.append((method, kwargs))
            if method == "HEAD":
                return {"status": 405, "headers": {}, "body": b""}
            return {"status": 206, "headers": {"content-type": "video/webm"}, "body": b"x"}

        result = verify_media(
            {"provider": "direct", "canonicalUrl": "https://cdn.hospital.example/lesson.webm"},
            hospital_hosts={"cdn.hospital.example"},
            http_request=request,
        )
        self.assertEqual(result["availabilityStatus"], "available")
        self.assertEqual(calls[1][0], "GET")
        self.assertEqual(calls[1][1]["headers"], {"Range": "bytes=0-0"})
        self.assertEqual(calls[1][1]["max_bytes"], 1024)


class ExternalMediaPersistence80Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "external-media.sqlite"

        def connect():
            conn = sqlite3.connect(self.path)
            conn.row_factory = sqlite3.Row
            conn.isolation_level = None
            return conn, "sqlite"

        self.connect = connect
        conn, kind = connect()
        try:
            conn.executescript(
                """
                CREATE TABLE materials (
                    id TEXT PRIMARY KEY, filename TEXT, title TEXT, description TEXT, category TEXT,
                    group_key TEXT, training_area TEXT, course_id TEXT, folder TEXT, page_count INTEGER,
                    date_added TEXT, storage_filename TEXT, storage_backend TEXT, storage_key TEXT,
                    slides_prefix TEXT, storage_meta TEXT, material_type TEXT, atlas_meta TEXT, active INTEGER
                );
                CREATE TABLE external_media (
                    id TEXT PRIMARY KEY, material_id TEXT NOT NULL UNIQUE, provider TEXT NOT NULL,
                    canonical_url TEXT NOT NULL, video_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                """
            )
            migrations._external_media_verification_80(conn, kind)
            conn.execute(
                "INSERT INTO materials VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "m1", "external.mp4", "Lesson", "", "", "grpBio", "internal", "", "m1", 0,
                    "2026-09-19T00:00:00+00:00", "external.mp4", "external", "", "", "{}", "video", "{}", 1,
                ),
            )
            conn.execute(
                "INSERT INTO external_media(id,material_id,provider,canonical_url,video_id,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (
                    "m1", "m1", "youtube", "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    "dQw4w9WgXcQ", "2026-09-19T00:00:00+00:00", "2026-09-19T00:00:00+00:00",
                ),
            )
        finally:
            conn.close()
        self.db_patch = patch("teacher_app.common.db.get_connection", side_effect=connect)
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)

    def test_migration_release_and_persistence_do_not_change_material_visibility(self):
        self.assertIn("0080-external-media-verification", release_contract.REQUIRED_MIGRATIONS)
        self.assertLess(
            release_contract.REQUIRED_MIGRATIONS.index("0079-provider-publish-receipts"),
            release_contract.REQUIRED_MIGRATIONS.index("0080-external-media-verification"),
        )
        conn, _ = self.connect()
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(external_media)").fetchall()}
            indexes = {row[1] for row in conn.execute("PRAGMA index_list(external_media)").fetchall()}
        finally:
            conn.close()
        self.assertTrue({"last_verified_at", "availability_status", "last_error", "provider_metadata"}.issubset(columns))
        self.assertIn("idx_external_media_availability", indexes)

        verified = external_media.verify_external_media(
            "m1",
            http_request=lambda *_args, **_kwargs: {
                "status": 200,
                "headers": {"content-type": "application/json"},
                "body": b'{"title":"Lesson"}',
            },
        )
        self.assertEqual(verified["availabilityStatus"], "available")
        report = external_media.list_external_media_report(status="available")
        self.assertEqual([item["materialId"] for item in report], ["m1"])
        conn, _ = self.connect()
        try:
            self.assertEqual(conn.execute("SELECT active FROM materials WHERE id='m1'").fetchone()[0], 1)
            self.assertEqual(
                conn.execute("SELECT availability_status FROM external_media WHERE material_id='m1'").fetchone()[0],
                "available",
            )
        finally:
            conn.close()

    def test_report_and_verify_route_keep_auditor_read_only(self):
        app = Flask(__name__)
        app.config.update(
            TESTING=True,
            EXTERNAL_MEDIA_HOSPITAL_CDN_HOSTS=(),
        )
        actor = {"username": "audit", "role": "auditor"}

        @app.before_request
        def bind_actor():
            g.teacher_user = actor

        register_external_media(app)
        client = app.test_client()
        report = client.get("/api/external-media/report")
        self.assertEqual(report.status_code, 200, report.get_data(as_text=True))
        self.assertTrue(report.get_json()["readOnly"])

        denied = client.post("/api/materials/m1/external-media/verify", json={})
        self.assertEqual(denied.status_code, 403)

        actor.clear()
        actor.update({"username": "root", "role": "system_admin"})
        with patch(
            "teacher_app.materials.external_media_routes.external_media_service.verify_external_media",
            return_value={
                "provider": "youtube",
                "availabilityStatus": "available",
                "lastVerifiedAt": "2026-09-19T00:00:00+00:00",
            },
        ):
            allowed = client.post("/api/materials/m1/external-media/verify", json={})
        self.assertEqual(allowed.status_code, 200, allowed.get_data(as_text=True))

        actor.clear()
        actor.update({"username": "student", "role": "student"})
        self.assertEqual(client.get("/api/external-media/report").status_code, 403)
        rule = next(rule for rule in app.url_map.iter_rules() if rule.rule == "/api/external-media/report")
        self.assertEqual(set(rule.methods) - {"HEAD", "OPTIONS"}, {"GET"})

    def test_periodic_maintenance_is_bounded_and_uses_explicit_env_hosts(self):
        with patch.dict(
            os.environ,
            {"EXTERNAL_MEDIA_HOSPITAL_CDN_HOSTS": "cdn.hospital.example"},
            clear=False,
        ), patch.object(
            external_media,
            "verify_due_external_media",
            return_value={"checked": 0, "counts": {}, "items": []},
        ) as verify:
            result = maintenance_verify.run_periodic_verification(
                older_than_minutes=360,
                limit=100,
            )
        self.assertEqual(result["checked"], 0)
        self.assertEqual(verify.call_args.kwargs["allow_hosts"], ("cdn.hospital.example",))
        self.assertEqual(verify.call_args.kwargs["older_than_minutes"], 360)
        self.assertEqual(verify.call_args.kwargs["limit"], 100)


if __name__ == "__main__":
    unittest.main()
