import datetime as dt
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from teacher_app.common import db as common_db
from teacher_app.maintenance.operational_incident_migration import operational_incidents_108
from teacher_app.notifications import incidents


class OperationalIncidents0108Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "incidents.sqlite"

        def connect():
            conn = sqlite3.connect(str(self.path), timeout=30)
            conn.row_factory = sqlite3.Row
            conn.isolation_level = None
            return conn, "sqlite"

        self.connect = connect
        conn, _kind = self.connect()
        try:
            operational_incidents_108(conn, "sqlite")
        finally:
            conn.close()
        patcher = patch.object(common_db, "get_connection", side_effect=self.connect)
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def candidate():
        return {
            "incidentKey": "worker_offline:lab-pc",
            "incidentType": "worker_offline",
            "category": "worker",
            "severity": "critical",
            "title": "教材 Worker 已離線",
            "detail": "lab-pc 已超過 10 分鐘未回報心跳。",
            "action": "重新啟動院內 Worker；不要重新上傳教材。",
            "errorCode": "WORKER_OFFLINE",
            "resourceId": "lab-pc-TeacherWorker",
        }

    def test_incident_stays_single_until_resolved_then_reopens_new_generation(self):
        t1 = dt.datetime(2026, 10, 3, 12, 0, tzinfo=dt.timezone.utc)
        first = incidents.sync_operational_incidents(
            now=t1,
            candidates=[self.candidate()],
        )
        self.assertEqual(len(first["opened"]), 1)
        self.assertEqual(first["opened"][0]["generation"], 1)
        self.assertEqual(len(first["active"]), 1)

        repeat = incidents.sync_operational_incidents(
            now=t1 + dt.timedelta(minutes=10),
            candidates=[self.candidate()],
        )
        self.assertEqual(repeat["opened"], [])
        self.assertEqual(repeat["reopened"], [])
        self.assertEqual(repeat["resolved"], [])
        self.assertEqual(repeat["active"][0]["generation"], 1)
        self.assertEqual(repeat["active"][0]["occurrenceCount"], 1)

        recovered = incidents.sync_operational_incidents(
            now=t1 + dt.timedelta(minutes=20),
            candidates=[],
        )
        self.assertEqual(len(recovered["resolved"]), 1)
        self.assertEqual(recovered["active"], [])
        recent = incidents.list_recent_incidents(
            now=t1 + dt.timedelta(minutes=20),
            resolved_hours=24,
        )
        self.assertEqual(recent[0]["status"], "resolved")
        self.assertEqual(recent[0]["generation"], 1)

        reopened = incidents.sync_operational_incidents(
            now=t1 + dt.timedelta(minutes=30),
            candidates=[self.candidate()],
        )
        self.assertEqual(len(reopened["reopened"]), 1)
        self.assertEqual(reopened["reopened"][0]["generation"], 2)
        self.assertEqual(reopened["reopened"][0]["occurrenceCount"], 2)
        self.assertEqual(reopened["active"][0]["generation"], 2)

    def test_multiple_candidates_resolve_independently(self):
        now = dt.datetime(2026, 10, 3, 12, 0, tzinfo=dt.timezone.utc)
        stalled = {
            "incidentKey": "job_stalled:job-a",
            "incidentType": "job_stalled",
            "category": "worker",
            "severity": "critical",
            "title": "教材處理工作可能卡住",
            "detail": "job-a stale",
            "action": "確認 Worker heartbeat",
            "errorCode": "WORKER_HEARTBEAT_STALLED",
            "resourceId": "job-a",
        }
        incidents.sync_operational_incidents(
            now=now,
            candidates=[self.candidate(), stalled],
        )
        result = incidents.sync_operational_incidents(
            now=now + dt.timedelta(minutes=10),
            candidates=[stalled],
        )
        self.assertEqual([row["incidentType"] for row in result["resolved"]], ["worker_offline"])
        self.assertEqual([row["incidentType"] for row in result["active"]], ["job_stalled"])


if __name__ == "__main__":
    unittest.main()
