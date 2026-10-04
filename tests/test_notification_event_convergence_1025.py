import datetime as dt
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from teacher_app.command_center.routes import register_training_command_center
from teacher_app.notifications import events


ROOT = Path(__file__).parents[1]
NOW = dt.datetime(2026, 10, 1, 12, 0, tzinfo=dt.timezone.utc)
USER = {"username":"s1","name":"學員","empId":"E1","role":"student","preferredArea":"internal","preferredGroup":"grpBio"}


class NotificationEventConvergence1025Tests(unittest.TestCase):
    def test_events_project_command_center_without_recalculating_course_completion(self):
        command = {"items":[{
            "id":"a1","resourceId":"c1","courseId":"c1","persona":"learner","domain":"learning","kind":"course",
            "title":"必修課","status":"pending","statusLabel":"待完成課程","group":"grpBio","area":"internal",
            "dueAt":"2026-10-03T12:00:00+00:00","overdue":False,"detail":"教材 0/1","target":"materials",
        }]}
        with patch.object(events.service,"build_summary",return_value=command), \
             patch.object(events.dashboard_service,"dashboard_summary",return_value={"pendingExams":[]}):
            data=events.build_events(USER,now=NOW)
        self.assertEqual(data["source"],"training-command-center")
        self.assertEqual(len(data["items"]),1)
        item=data["items"][0]
        self.assertEqual(item["kind"],"course")
        self.assertEqual(item["emailPolicy"],"due")
        self.assertIn("email",item["channels"])
        self.assertIn("courseId=c1",item["href"])

    def test_exam_window_only_augments_deadline_for_pending_canonical_exam(self):
        command={"items":[]}
        dashboard={"pendingExams":[{"id":"e1","title":"安全考核","area":"internal","group":"grpBio","courseId":"c1","passingScore":80}]}
        with patch.object(events.service,"build_summary",return_value=command), \
             patch.object(events.dashboard_service,"dashboard_summary",return_value=dashboard), \
             patch.object(events.exam_windows,"get_window",return_value={"closes_at":"2026-10-02T12:00:00+00:00","reminder_enabled":1}):
            data=events.build_events(USER,now=NOW)
        item=data["items"][0]
        self.assertEqual(item["kind"],"exam")
        self.assertEqual(item["resourceId"],"e1")
        self.assertEqual(item["dueAt"],"2026-10-02T12:00:00+00:00")
        self.assertEqual(item["emailPolicy"],"due")

    def test_system_admin_gets_worker_offline_event_and_other_roles_do_not(self):
        system_user={**USER,"username":"sys","role":"system_admin","roles":["system_admin"]}
        offline={
            "available":True,
            "thresholdSeconds":600,
            "workers":[{"workerId":"worker-a","lastSeen":"2026-10-02T00:45:00+00:00","offlineSeconds":900,"currentJobId":""}],
        }
        with patch.object(events.service,"build_summary",return_value={"items":[]}), \
             patch.object(events.dashboard_service,"dashboard_summary",return_value={"pendingExams":[]}), \
             patch.object(events.worker_operations,"offline_worker_alerts",return_value=offline):
            data=events.build_events(system_user,now=NOW)
        item=next(row for row in data["items"] if row["kind"]=="worker_offline")
        self.assertEqual(item["persona"],"system")
        self.assertEqual(item["emailPolicy"],"once")
        self.assertIn("email",item["channels"])
        self.assertIn("workspace=worker",item["href"])
        self.assertIn("persona=system",item["href"])

        with patch.object(events.service,"build_summary",return_value={"items":[]}), \
             patch.object(events.dashboard_service,"dashboard_summary",return_value={"pendingExams":[]}), \
             patch.object(events.worker_operations,"offline_worker_alerts") as alert:
            learner=events.build_events(USER,now=NOW)
        alert.assert_not_called()
        self.assertFalse(any(row["kind"]=="worker_offline" for row in learner["items"]))

    def test_worker_status_lookup_failure_never_becomes_offline_notification(self):
        system_user={**USER,"username":"sys","role":"system_admin","roles":["system_admin"]}
        with patch.object(events.service,"build_summary",return_value={"items":[]}), \
             patch.object(events.dashboard_service,"dashboard_summary",return_value={"pendingExams":[]}), \
             patch.object(events.worker_operations,"offline_worker_alerts",return_value={"available":False,"thresholdSeconds":600,"workers":[]}):
            data=events.build_events(system_user,now=NOW)
        self.assertFalse(any(row["kind"]=="worker_offline" for row in data["items"]))

    def test_worker_outage_key_is_stable_until_a_new_heartbeat_outage(self):
        system_user={**USER,"username":"sys","role":"system_admin","roles":["system_admin"]}
        def build(last_seen):
            with patch.object(events.service,"build_summary",return_value={"items":[]}), \
                 patch.object(events.dashboard_service,"dashboard_summary",return_value={"pendingExams":[]}), \
                 patch.object(events.worker_operations,"offline_worker_alerts",return_value={
                     "available":True,"thresholdSeconds":600,
                     "workers":[{"workerId":"worker-a","lastSeen":last_seen,"offlineSeconds":900,"currentJobId":""}],
                 }):
                return next(row for row in events.build_events(system_user,now=NOW)["items"] if row["kind"]=="worker_offline")
        first=build("2026-10-02T00:45:00+00:00")
        replay=build("2026-10-02T00:45:00+00:00")
        later_outage=build("2026-10-02T00:48:00+00:00")
        self.assertEqual(first["key"],replay["key"])
        self.assertNotEqual(first["key"],later_outage["key"])

    def test_system_admin_gets_persisted_operational_incident_and_recovery_events(self):
        system_user={**USER,"username":"sys","role":"system_admin","roles":["system_admin"]}
        rows=[
            {
                "incidentKey":"error_burst:r2_storage",
                "incidentType":"error_burst",
                "category":"storage",
                "severity":"critical",
                "status":"open",
                "title":"教材背景工作連續發生 R2_STORAGE",
                "detail":"最近已連續 3 筆工作以相同 error code 失敗。",
                "action":"確認 R2 bucket 與網路。",
                "errorCode":"R2_STORAGE",
                "resourceId":"R2_STORAGE",
                "generation":1,
                "occurrenceCount":1,
                "openedAt":"2026-10-01T11:00:00+00:00",
                "lastSeenAt":"2026-10-01T12:00:00+00:00",
                "resolvedAt":"",
            },
            {
                "incidentKey":"job_stalled:job-old",
                "incidentType":"job_stalled",
                "category":"worker",
                "severity":"critical",
                "status":"resolved",
                "title":"教材處理工作可能卡住",
                "detail":"job-old stale",
                "action":"確認 Worker heartbeat",
                "errorCode":"WORKER_HEARTBEAT_STALLED",
                "resourceId":"job-old",
                "generation":2,
                "occurrenceCount":2,
                "openedAt":"2026-10-01T09:00:00+00:00",
                "lastSeenAt":"2026-10-01T11:50:00+00:00",
                "resolvedAt":"2026-10-01T11:50:00+00:00",
            },
        ]
        with patch.object(events.service,"build_summary",return_value={"items":[]}), \
             patch.object(events.dashboard_service,"dashboard_summary",return_value={"pendingExams":[]}), \
             patch.object(events.incidents,"list_recent_incidents",return_value=rows), \
             patch.object(events.worker_operations,"offline_worker_alerts",return_value={"available":True,"thresholdSeconds":600,"workers":[]}):
            data=events.build_events(system_user,now=NOW)

        incident=next(row for row in data["items"] if row["kind"]=="operational_incident")
        recovery=next(row for row in data["items"] if row["kind"]=="operational_recovery")
        self.assertEqual(incident["errorCode"],"R2_STORAGE")
        self.assertEqual(incident["generation"],1)
        self.assertEqual(incident["emailPolicy"],"once")
        self.assertIn("workspace=worker",incident["href"])
        self.assertEqual(recovery["generation"],2)
        self.assertIn("已恢復",recovery["title"])
        self.assertNotEqual(incident["key"],recovery["key"])

    def test_email_filter_reuses_same_events_and_horizon(self):
        rows={"items":[
            {"key":"soon","kind":"course","channels":["in_app","email"],"emailPolicy":"due","dueAt":"2026-10-02T12:00:00+00:00"},
            {"key":"later","kind":"course","channels":["in_app","email"],"emailPolicy":"due","dueAt":"2026-10-10T12:00:00+00:00"},
            {"key":"failure","kind":"material_failure","channels":["in_app","email"],"emailPolicy":"once","dueAt":""},
        ]}
        with patch.object(events,"build_events",return_value=rows):
            selected=events.email_events(USER,now=NOW,days=3)
        self.assertEqual([row["key"] for row in selected],["soon","failure"])

    def test_due_email_uses_separate_7_3_1_day_milestone_keys(self):
        due="2026-10-08T12:00:00+00:00"
        rows={"items":[{"key":"exam-base","kind":"exam","channels":["in_app","email"],"emailPolicy":"due","dueAt":due,"detail":"考核已設定最後作答時間"}]}
        with patch.object(events,"build_events",return_value=rows):
            seven=events.email_events(USER,now=NOW,days=7)
            three=events.email_events(USER,now=NOW+dt.timedelta(days=4),days=7)
            one=events.email_events(USER,now=NOW+dt.timedelta(days=6),days=7)
        self.assertEqual(seven[0]["reminderMilestoneDays"],7)
        self.assertEqual(three[0]["reminderMilestoneDays"],3)
        self.assertEqual(one[0]["reminderMilestoneDays"],1)
        self.assertEqual(len({seven[0]["key"],three[0]["key"],one[0]["key"]}),3)

    def test_due_email_does_not_send_after_deadline(self):
        rows={"items":[{"key":"exam-base","kind":"exam","channels":["in_app","email"],"emailPolicy":"due","dueAt":"2026-09-30T12:00:00+00:00"}]}
        with patch.object(events,"build_events",return_value=rows):
            self.assertEqual(events.email_events(USER,now=NOW,days=7),[])

    def test_notifications_route_is_get_only(self):
        app=Flask(__name__);app.config.update(TESTING=True,SECRET_KEY="test")
        owner=SimpleNamespace(app=app,_current_user=lambda:USER)
        register_training_command_center(owner)
        client=app.test_client()
        expected={"items":[],"counts":{"total":0},"source":"training-command-center"}
        with patch("teacher_app.command_center.routes.notification_events.build_events",return_value=expected):
            response=client.get('/api/training-command-center/notifications')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.get_json(),expected)
        self.assertEqual(client.post('/api/training-command-center/notifications').status_code,405)

    def test_email_sender_consumes_events_not_parallel_domain_queries(self):
        source=ROOT.joinpath('teacher_app','notifications','reminders.py').read_text(encoding='utf-8')
        self.assertIn('events.email_events',source)
        for forbidden in ('assignment_service','progress_service','SELECT w.quiz_category_id','exam_records WHERE'):
            self.assertNotIn(forbidden,source)
        self.assertIn('email_notification_log',source)
        self.assertIn('_release_claim',source)


if __name__=='__main__':
    unittest.main()
