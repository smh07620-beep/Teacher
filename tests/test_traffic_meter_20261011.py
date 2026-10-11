import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import datetime as dt

from flask import Flask, Response, g

import release_contract
from teacher_app.common import db as common_db
from teacher_app.maintenance import traffic_meter
from teacher_app.maintenance.traffic_meter import TrafficMeter, bucket_for, register_traffic_meter, thresholds_gb


class BucketTests(unittest.TestCase):
    def test_buckets_are_coarse_and_carry_no_ids_or_names(self):
        self.assertEqual(bucket_for("/api/slides/abc-123/versions"), "api/slides")
        self.assertEqual(bucket_for("/api/auth/login"), "api/auth")
        self.assertEqual(bucket_for("/uploaded-slides/mat-1/slide-01.webp"), "media/uploaded-slides")
        self.assertEqual(bucket_for("/material-preview/mat-1/page/3.png"), "media/material-preview")
        self.assertEqual(bucket_for("/static/app.js"), "static")
        self.assertEqual(bucket_for("/system-learner.js"), "static")
        self.assertEqual(bucket_for("/pgy"), "page")
        for path in ("/api/slides/王小明/x", "/view/secret-name"):
            self.assertNotIn("王小明", bucket_for(path))
            self.assertNotIn("secret", bucket_for(path))

    def test_thresholds_parse_and_ignore_garbage(self):
        self.assertEqual(thresholds_gb({"TRAFFIC_ALERT_GB": "3.5, 2.5,abc,-1,0"}), [2.5, 3.5])
        self.assertEqual(thresholds_gb({}), [2.5, 3.5])


class MeterDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = mock.patch.dict(
            os.environ,
            {"DATABASE_URL": "", "TEACHER_SQLITE_PATH": str(Path(self.tmp.name) / "t.db"), "TRAFFIC_ALERT_EMAIL": "admin@example.org"},
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        conn, kind = common_db.get_connection()
        try:
            from teacher_app.maintenance.traffic_meter_migration import traffic_meter_119

            traffic_meter_119(conn, kind)
        finally:
            conn.close()
        self.now = dt.datetime(2026, 10, 14, 9, 0, tzinfo=dt.timezone.utc)
        self.mails = []
        self.clock = [1000.0]
        self.meter = TrafficMeter(
            clock=lambda: self.clock[0],
            utcnow=lambda: self.now,
            mailer=lambda to, subject, body: self.mails.append((to, subject, body)) or True,
        )

    def test_flush_accumulates_per_day_and_bucket(self):
        self.meter.record("api/slides", 1000)
        self.meter.record("api/slides", 500)
        self.meter.record("static", 200)
        self.meter.flush()
        self.meter.record("api/slides", 100)
        self.meter.flush()
        summary = self.meter.month_summary("2026-10")
        by = {b["bucket"]: b for b in summary["buckets"]}
        self.assertEqual(by["api/slides"]["bytes"], 1600)
        self.assertEqual(by["api/slides"]["requests"], 3)
        self.assertEqual(summary["totalBytes"], 1800)
        self.assertEqual(self.meter.month_summary("2026-09")["totalBytes"], 0)

    def test_alert_sent_once_per_threshold_and_names_no_users(self):
        gb = 1024**3
        self.meter.record("media/uploaded-slides", int(2.6 * gb))
        self.meter.flush()
        self.assertEqual(len(self.mails), 1)
        to, subject, body = self.mails[0]
        self.assertEqual(to, "admin@example.org")
        self.assertIn("2.5 GB", subject)
        self.assertIn("media/uploaded-slides", body)
        self.clock[0] += 3600
        self.meter.record("static", 10)
        self.meter.flush()
        self.assertEqual(len(self.mails), 1, "same threshold must not be mailed twice")
        self.meter.record("media/uploaded-slides", int(1.0 * gb))
        self.clock[0] += 3600
        self.meter.flush()
        self.assertEqual(len(self.mails), 2)
        self.assertIn("3.5 GB", self.mails[1][1])

    def test_failed_mail_is_retried_later_not_marked_sent(self):
        gb = 1024**3
        outcomes = [False, True]
        sent = []
        meter = TrafficMeter(
            clock=lambda: self.clock[0],
            utcnow=lambda: self.now,
            mailer=lambda *a: sent.append(a) or outcomes.pop(0),
        )
        meter.record("static", int(2.6 * gb))
        meter.flush()
        self.assertEqual(len(sent), 1)
        meter.record("static", 1)
        meter.flush()
        self.assertEqual(len(sent), 1, "must wait before retrying")
        self.clock[0] += 16 * 60
        meter.record("static", 1)
        meter.flush()
        self.assertEqual(len(sent), 2)
        self.assertIn("2.5", meter.month_summary()["alertsSent"])

    def test_no_recipient_means_no_mail_but_usage_still_recorded(self):
        with mock.patch.dict(os.environ, {"TRAFFIC_ALERT_EMAIL": ""}):
            self.meter.record("static", int(3 * 1024**3))
            self.meter.flush()
            self.assertFalse(self.meter.month_summary()["emailConfigured"])
        self.assertEqual(self.mails, [])
        self.assertGreater(self.meter.month_summary()["totalGb"], 2.9)

    def test_database_failure_never_raises(self):
        with mock.patch.object(common_db, "transaction", side_effect=RuntimeError("db down")):
            self.meter.record("static", 10)
            self.meter.flush()  # must not raise

    def test_bucket_cardinality_is_capped(self):
        for i in range(traffic_meter.MAX_BUCKETS + 40):
            self.meter.record(f"api/x{i}", 1)
        self.meter.flush()
        names = {b["bucket"] for b in self.meter.month_summary()["buckets"]}
        self.assertIn("other", {b["bucket"] for b in self.meter.month_summary()["buckets"]} | names)


class RouteTests(unittest.TestCase):
    def build(self, user):
        app = Flask(__name__)
        app.config["TESTING"] = True
        meter = mock.Mock()
        meter.month_summary.return_value = {"month": "2026-10", "totalBytes": 5, "totalGb": 0.0}
        register_traffic_meter(app, meter=meter)

        @app.get("/hello")
        def hello():
            return Response("hello", mimetype="text/plain")

        @app.before_request
        def inject():
            if user:
                g.teacher_user = user

        return app, meter

    def test_requests_are_counted_with_bucket_and_size(self):
        app, meter = self.build(None)
        app.test_client().get("/hello")
        meter.record.assert_called_once_with("page", 5)

    def test_endpoint_requires_login_and_storage_permission(self):
        app, _ = self.build(None)
        self.assertEqual(app.test_client().get("/api/admin/traffic-usage").status_code, 401)
        for role in ("student", "clinical_teacher", "auditor"):
            app, _ = self.build({"username": "s", "role": role})
            self.assertEqual(app.test_client().get("/api/admin/traffic-usage").status_code, 403, role)
        app, meter = self.build({"username": "a", "role": "system_admin"})
        response = app.test_client().get("/api/admin/traffic-usage")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["month"], "2026-10")
        meter.flush.assert_called_once()

    def test_switch_off(self):
        app, meter = self.build(None)
        with mock.patch.dict(os.environ, {"TRAFFIC_METER": "false"}):
            app.test_client().get("/hello")
        meter.record.assert_not_called()


class ContractTests(unittest.TestCase):
    def test_migration_is_in_release_contract_last(self):
        self.assertEqual(release_contract.REQUIRED_MIGRATIONS[-1], "0119-traffic-meter")


if __name__ == "__main__":
    unittest.main()
