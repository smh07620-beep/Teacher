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
    def _create_ai_job_tables(self):
        conn, _kind = self.connect()
        try:
            for _queue, table, _label, _code in incidents._AI_QUEUE_SPECS:
                conn.execute(
                    f"CREATE TABLE IF NOT EXISTS {table} ("
                    "id TEXT PRIMARY KEY,status TEXT NOT NULL,error TEXT NOT NULL DEFAULT '',"
                    "updated_at TEXT NOT NULL)"
                )
        finally:
            conn.close()

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

    def test_ai_failure_burst_opens_once_and_success_resolves_without_raw_error(self):
        self._create_ai_job_tables()
        now = dt.datetime(2026, 10, 3, 13, 0, tzinfo=dt.timezone.utc)
        conn, _kind = self.connect()
        try:
            conn.execute(
                "INSERT INTO ai_question_jobs(id,status,error,updated_at) VALUES(?,?,?,?)",
                ("q-1", "failed", "api_key=do-not-log", (now - dt.timedelta(minutes=2)).isoformat()),
            )
            conn.execute(
                "INSERT INTO ai_question_jobs(id,status,error,updated_at) VALUES(?,?,?,?)",
                ("q-2", "failed", "token=do-not-log", (now - dt.timedelta(minutes=1)).isoformat()),
            )
        finally:
            conn.close()

        with patch.object(
            incidents.worker_operations,
            "operational_incident_candidates",
            return_value=[],
        ), patch.object(
            incidents.worker_operations,
            "online_worker_recovery_keys",
            return_value=set(),
        ):
            opened = incidents.sync_operational_incidents(now=now)

        self.assertEqual(len(opened["opened"]), 1)
        item = opened["opened"][0]
        self.assertEqual(item["incidentType"], "ai_queue_failure")
        self.assertEqual(item["resourceId"], "question")
        self.assertEqual(item["errorCode"], "AI_QUESTION_FAILURE_BURST")
        self.assertNotIn("do-not-log", item["detail"])

        conn, _kind = self.connect()
        try:
            conn.execute(
                "INSERT INTO ai_question_jobs(id,status,error,updated_at) VALUES(?,?,?,?)",
                ("q-3", "completed", "", (now + dt.timedelta(minutes=1)).isoformat()),
            )
        finally:
            conn.close()

        with patch.object(
            incidents.worker_operations,
            "operational_incident_candidates",
            return_value=[],
        ), patch.object(
            incidents.worker_operations,
            "online_worker_recovery_keys",
            return_value=set(),
        ):
            recovered = incidents.sync_operational_incidents(
                now=now + dt.timedelta(minutes=2)
            )
        self.assertEqual(len(recovered["resolved"]), 1)
        self.assertEqual(recovered["resolved"][0]["incidentType"], "ai_queue_failure")
        self.assertEqual(recovered["active"], [])

    def test_active_incidents_sort_critical_before_warning(self):
        now = dt.datetime(2026, 10, 3, 14, 0, tzinfo=dt.timezone.utc)
        warning = {
            **self.candidate(),
            "incidentKey": "warning:test",
            "incidentType": "warning_test",
            "severity": "warning",
            "title": "Warning",
        }
        critical = {
            **self.candidate(),
            "incidentKey": "critical:test",
            "incidentType": "critical_test",
            "severity": "critical",
            "title": "Critical",
        }
        incidents.sync_operational_incidents(
            now=now,
            candidates=[warning, critical],
        )
        active = incidents.list_active_incidents()
        self.assertEqual([row["severity"] for row in active[:2]], ["critical", "warning"])

    def test_incident_read_failure_logs_only_error_type(self):
        with patch.object(
            incidents.common_db,
            "read_connection",
            side_effect=RuntimeError("password=do-not-log"),
        ), patch.object(incidents.LOGGER, "warning") as warning:
            self.assertEqual(incidents.list_active_incidents(), [])

        rendered = "\n".join(str(call) for call in warning.call_args_list)
        self.assertIn("operational incident read failed", rendered)
        self.assertIn("RuntimeError", rendered)
        self.assertNotIn("do-not-log", rendered)

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
