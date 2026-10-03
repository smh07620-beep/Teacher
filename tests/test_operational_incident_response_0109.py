import datetime as dt
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from teacher_app.command_center.notification_routes import register_notification_state_routes
from teacher_app.common import db as common_db
from teacher_app.maintenance.operational_incident_migration import operational_incidents_108
from teacher_app.maintenance.operational_incident_response_migration import operational_incident_response_109
from teacher_app.notifications import events, incidents


NOW = dt.datetime(2026, 10, 3, 12, 0, tzinfo=dt.timezone.utc)
SYSTEM_USER = {
    "username": "sys1",
    "name": "系統管理",
    "role": "system_admin",
    "roles": ["system_admin"],
}
LEARNER = {
    "username": "student1",
    "name": "學員",
    "role": "student",
    "roles": ["student"],
}


class OperationalIncidentResponse0109Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "incident-response.sqlite"

        def connect():
            conn = sqlite3.connect(str(self.path), timeout=30)
            conn.row_factory = sqlite3.Row
            conn.isolation_level = None
            return conn, "sqlite"

        self.connect = connect
        conn, _kind = connect()
        try:
            operational_incidents_108(conn, "sqlite")
            operational_incident_response_109(conn, "sqlite")
        finally:
            conn.close()
        db_patch = patch.object(common_db, "get_connection", side_effect=self.connect)
        db_patch.start()
        self.addCleanup(db_patch.stop)

    @staticmethod
    def candidate(code="R2_STORAGE"):
        return {
            "incidentKey": "error_burst:r2_storage",
            "incidentType": "error_burst",
            "category": "storage",
            "severity": "critical",
            "title": "教材背景工作連續發生 R2_STORAGE",
            "detail": "最近已連續 3 筆工作失敗。",
            "action": "確認 R2 bucket 與網路。",
            "errorCode": code,
            "resourceId": code,
        }

    def test_response_state_preserves_detection_state_and_runbook(self):
        opened = incidents.sync_operational_incidents(
            now=NOW,
            candidates=[self.candidate()],
        )["opened"][0]
        self.assertEqual(opened["status"], "open")
        self.assertEqual(opened["responseState"], "unacknowledged")
        self.assertEqual(opened["runbook"]["code"], "R2_STORAGE")
        self.assertTrue(opened["runbook"]["steps"])

        acknowledged = incidents.update_incident_response(
            opened["incidentKey"],
            actor_username="sys1",
            action="acknowledge",
            now=NOW + dt.timedelta(minutes=1),
        )
        self.assertEqual(acknowledged["status"], "open")
        self.assertEqual(acknowledged["responseState"], "acknowledged")
        self.assertEqual(acknowledged["acknowledgedBy"], "sys1")

        assigned = incidents.update_incident_response(
            opened["incidentKey"],
            actor_username="sys1",
            action="assign",
            assigned_to="sys2",
            now=NOW + dt.timedelta(minutes=2),
        )
        self.assertEqual(assigned["responseState"], "assigned")
        self.assertEqual(assigned["assignedTo"], "sys2")

        maintenance = incidents.update_incident_response(
            opened["incidentKey"],
            actor_username="sys1",
            action="maintenance",
            maintenance_minutes=60,
            now=NOW + dt.timedelta(minutes=3),
        )
        self.assertEqual(maintenance["status"], "open")
        self.assertEqual(maintenance["responseState"], "maintenance")
        self.assertTrue(maintenance["maintenanceActive"])

        refreshed = incidents.sync_operational_incidents(
            now=NOW + dt.timedelta(minutes=10),
            candidates=[self.candidate()],
        )["active"][0]
        self.assertEqual(refreshed["responseState"], "maintenance")
        self.assertEqual(refreshed["assignedTo"], "sys2")

    def test_recovery_keeps_response_history_but_new_generation_resets_it(self):
        incidents.sync_operational_incidents(now=NOW, candidates=[self.candidate()])
        incidents.update_incident_response(
            "error_burst:r2_storage",
            actor_username="sys1",
            action="assign",
            assigned_to="sys2",
            now=NOW + dt.timedelta(minutes=1),
        )
        incidents.update_incident_response(
            "error_burst:r2_storage",
            actor_username="sys1",
            action="note",
            note="已聯絡網路管理員",
            now=NOW + dt.timedelta(minutes=2),
        )

        resolved = incidents.sync_operational_incidents(
            now=NOW + dt.timedelta(minutes=3),
            candidates=[],
        )["resolved"][0]
        self.assertEqual(resolved["status"], "resolved")
        self.assertEqual(resolved["assignedTo"], "sys2")
        self.assertEqual(resolved["responseNote"], "已聯絡網路管理員")

        reopened = incidents.sync_operational_incidents(
            now=NOW + dt.timedelta(minutes=4),
            candidates=[self.candidate()],
        )["reopened"][0]
        self.assertEqual(reopened["generation"], 2)
        self.assertEqual(reopened["responseState"], "unacknowledged")
        self.assertEqual(reopened["assignedTo"], "")
        self.assertEqual(reopened["responseNote"], "")
        self.assertFalse(reopened["maintenanceActive"])

    def test_maintenance_suppresses_open_email_but_not_in_app_or_recovery(self):
        incidents.sync_operational_incidents(now=NOW, candidates=[self.candidate()])
        incidents.update_incident_response(
            "error_burst:r2_storage",
            actor_username="sys1",
            action="maintenance",
            maintenance_minutes=60,
            now=NOW,
        )

        with patch.object(events.service, "build_summary", return_value={"items": []}),              patch.object(events.dashboard_service, "dashboard_summary", return_value={"pendingExams": []}),              patch.object(events.worker_operations, "offline_worker_alerts", return_value={"available": True, "thresholdSeconds": 600, "workers": []}):
            open_rows = events.build_events(SYSTEM_USER, now=NOW + dt.timedelta(minutes=5))["items"]

        open_event = next(row for row in open_rows if row["kind"] == "operational_incident")
        self.assertEqual(open_event["channels"], ["in_app"])
        self.assertEqual(open_event["emailPolicy"], "none")
        self.assertTrue(open_event["maintenanceActive"])

        incidents.sync_operational_incidents(
            now=NOW + dt.timedelta(minutes=10),
            candidates=[],
        )
        with patch.object(events.service, "build_summary", return_value={"items": []}),              patch.object(events.dashboard_service, "dashboard_summary", return_value={"pendingExams": []}),              patch.object(events.worker_operations, "offline_worker_alerts", return_value={"available": True, "thresholdSeconds": 600, "workers": []}):
            recovery_rows = events.build_events(SYSTEM_USER, now=NOW + dt.timedelta(minutes=10))["items"]

        recovery = next(row for row in recovery_rows if row["kind"] == "operational_recovery")
        self.assertIn("email", recovery["channels"])
        self.assertEqual(recovery["emailPolicy"], "once")

    def test_response_api_is_system_admin_only_and_audited(self):
        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY="test")
        owner = SimpleNamespace(app=app, _current_user=lambda: SYSTEM_USER)
        register_notification_state_routes(owner)
        client = app.test_client()

        incident_result = {
            **self.candidate(),
            "status": "open",
            "responseState": "acknowledged",
            "assignedTo": "",
            "maintenanceUntil": "",
            "generation": 1,
        }
        with patch("teacher_app.command_center.notification_routes.incidents.update_incident_response", return_value=incident_result) as update,              patch("teacher_app.command_center.notification_routes.audit.record_event") as audit:
            response = client.patch(
                "/api/operational-incidents/error_burst:r2_storage",
                json={"action": "acknowledge"},
            )
        self.assertEqual(response.status_code, 200)
        update.assert_called_once()
        audit.assert_called_once()
        self.assertEqual(audit.call_args.kwargs["action"], "operational.incident.acknowledge")

        learner_app = Flask(__name__)
        learner_app.config.update(TESTING=True, SECRET_KEY="test")
        learner_owner = SimpleNamespace(app=learner_app, _current_user=lambda: LEARNER)
        register_notification_state_routes(learner_owner)
        learner_client = learner_app.test_client()
        denied = learner_client.patch(
            "/api/operational-incidents/error_burst:r2_storage",
            json={"action": "acknowledge"},
        )
        self.assertEqual(denied.status_code, 403)

    def test_assign_api_rejects_non_system_admin_assignee(self):
        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY="test")
        owner = SimpleNamespace(app=app, _current_user=lambda: SYSTEM_USER)
        register_notification_state_routes(owner)
        client = app.test_client()

        with patch(
            "teacher_app.command_center.notification_routes.auth_repository.find_user",
            return_value={"username": "teacher1", "active": True, "role": "clinical_teacher", "roles_json": '["clinical_teacher"]'},
        ):
            response = client.patch(
                "/api/operational-incidents/error_burst:r2_storage",
                json={"action": "assign", "assignedTo": "teacher1"},
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["code"], "INVALID_INCIDENT_ASSIGNEE")


if __name__ == "__main__":
    unittest.main()
