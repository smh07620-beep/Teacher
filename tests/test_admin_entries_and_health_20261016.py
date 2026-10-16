import datetime as dt
import unittest

from teacher_app.admin import health_overview as health


class HealthLightsTests(unittest.TestCase):
    now = dt.datetime(2026, 10, 16, 12, 0, tzinfo=dt.timezone.utc)

    def test_database_light_levels(self):
        self.assertEqual(health.database_light({"database": {"ok": True}, "migrations": {"ok": True}})["state"], "green")
        self.assertEqual(health.database_light({"database": {"ok": True}, "migrations": {"ok": False, "missing": ["x"]}})["state"], "yellow")
        self.assertEqual(health.database_light({"database": {"ok": False}, "migrations": {}})["state"], "red")

    def test_worker_light_by_heartbeat_age(self):
        def beat(minutes):
            return {"worker_id": "w", "last_seen": (self.now - dt.timedelta(minutes=minutes)).isoformat()}

        self.assertEqual(health.worker_lights([beat(3)], self.now)[0]["state"], "green")
        self.assertEqual(health.worker_lights([beat(30)], self.now)[0]["state"], "yellow")
        self.assertEqual(health.worker_lights([beat(300)], self.now)[0]["state"], "red")
        self.assertEqual(health.worker_lights([], self.now)[0]["state"], "red")

    def test_storage_and_traffic_lights(self):
        gb = 1024 ** 3
        self.assertEqual(health.storage_light(1 * gb, 10 * gb)["state"], "green")
        self.assertEqual(health.storage_light(8 * gb, 10 * gb)["state"], "yellow")
        self.assertEqual(health.storage_light(10 * gb, 10 * gb)["state"], "red")
        self.assertEqual(health.storage_light(1 * gb, None)["state"], "gray")
        self.assertEqual(health.storage_light(None, None)["state"], "gray")
        self.assertEqual(health.traffic_light(0)["state"], "green")
        self.assertEqual(health.traffic_light(2)["state"], "yellow")
        self.assertEqual(health.traffic_light(None)["state"], "gray")


class EntryRoutesTests(unittest.TestCase):
    def test_teach_and_admin_send_visitors_to_login_then_to_the_workspace(self):
        import pgy_app

        client = pgy_app.app.test_client()
        for path in ("/teach", "/admin"):
            response = client.get(path)
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.headers["Location"].startswith("/login?next=%2F"))

    def test_health_overview_requires_an_admin(self):
        import pgy_app

        client = pgy_app.app.test_client()
        self.assertIn(client.get("/api/admin/health-overview").status_code, (401, 403))


if __name__ == "__main__":
    unittest.main()
