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

    def test_email_filter_reuses_same_events_and_horizon(self):
        rows={"items":[
            {"key":"soon","kind":"course","channels":["in_app","email"],"emailPolicy":"due","dueAt":"2026-10-02T12:00:00+00:00"},
            {"key":"later","kind":"course","channels":["in_app","email"],"emailPolicy":"due","dueAt":"2026-10-10T12:00:00+00:00"},
            {"key":"failure","kind":"material_failure","channels":["in_app","email"],"emailPolicy":"once","dueAt":""},
        ]}
        with patch.object(events,"build_events",return_value=rows):
            selected=events.email_events(USER,now=NOW,days=3)
        self.assertEqual([row["key"] for row in selected],["soon","failure"])

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
