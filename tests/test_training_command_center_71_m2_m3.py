"""Teacher 7.1 M2/M3 competency-matrix and learning-analytics regressions."""
import datetime as dt
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from teacher_app.command_center import analytics, competency, scope
from teacher_app.command_center.routes import register_training_command_center
from teacher_app.common.errors import ApiError


ROOT = Path(__file__).parents[1]
NOW = dt.datetime(2026, 9, 16, 12, 0, tzinfo=dt.timezone.utc)
LEARNER = {
    "username": "s1",
    "name": "學員一",
    "empId": "E001",
    "group": "grpHema",
    "pgyLearner": True,
}


class CommandCenterScopeTests(unittest.TestCase):
    def test_multi_role_teacher_group_leader_uses_group_scope(self):
        user = {
            "username": "leader1",
            "role": "clinical_teacher",
            "roles": ["clinical_teacher", "group_leader"],
            "preferredGroup": "grpHema",
        }
        resolved = scope.resolve_scope(user)
        self.assertEqual(resolved["kind"], "group")
        self.assertEqual(resolved["group"], "grpHema")
        self.assertIn("clinical_teacher", resolved["roles"])
        self.assertIn("group_leader", resolved["roles"])

    def test_system_admin_and_auditor_do_not_gain_learner_analytics_scope(self):
        for role in ("system_admin", "auditor"):
            with self.subTest(role=role):
                with self.assertRaises(ApiError) as raised:
                    scope.resolve_scope({"username": role, "role": role, "preferredGroup": "grpHema"})
                self.assertEqual(raised.exception.status, 403)


class CompetencyMatrixProjectionTests(unittest.TestCase):
    def test_matrix_uses_formal_assessment_tools_and_assignment_progress_only(self):
        assignments = [
            {"id":"a1","learner_username":"s1","group_key":"grpHema","title":"已完成訓練","due_at":"2026-09-14T12:00:00+00:00","status":"finalized","updated_at":"2026-09-15T08:00:00+00:00"},
            {"id":"a2","learner_username":"s1","group_key":"grpHema","title":"逾期訓練","due_at":"2026-09-15T12:00:00+00:00","status":"assigned","updated_at":"2026-09-15T08:00:00+00:00"},
        ]
        assessments = [
            {"id":"p1","assessment_type":"dops","emp_id":"E001","overall_score":4,"status":"completed","assessment_date":"2026-09-10","created_at":"2026-09-10T09:00:00+00:00"},
            {"id":"p2","assessment_type":"dops","emp_id":"E001","overall_score":5,"status":"completed","assessment_date":"2026-09-12","created_at":"2026-09-12T09:00:00+00:00"},
            {"id":"legacy","assessment_type":"core6","emp_id":"E001","overall_score":5,"status":"completed","assessment_date":"2026-09-13","created_at":"2026-09-13T09:00:00+00:00"},
        ]
        data = competency.project_matrix({"kind":"self","roles":["student"],"group":"grpHema"}, [LEARNER], assignments, assessments, now=NOW)
        row = data["learners"][0]
        self.assertEqual(row["progress"]["assignmentsTotal"], 2)
        self.assertEqual(row["progress"]["assignmentsCompleted"], 1)
        self.assertEqual(row["progress"]["assignmentsOverdue"], 1)
        self.assertEqual(row["progress"]["percent"], 50.0)
        self.assertEqual(row["competencies"]["dops"]["count"], 2)
        self.assertEqual(row["competencies"]["dops"]["averageScore"], 4.5)
        self.assertEqual(row["competencies"]["dops"]["latestScore"], 5.0)
        self.assertEqual(data["summary"]["assessments"], 2)
        self.assertEqual(data["interpretation"], "matrix_by_formal_assessment_tool")
        self.assertNotIn("mastery", row)
        self.assertNotIn("core6", row["competencies"])


class LearningAnalyticsProjectionTests(unittest.TestCase):
    def test_analytics_describe_existing_records_without_synthetic_mastery(self):
        learning_rows = [
            {"material_id":"m1","username":"s1","progress":50,"completed":0,"last_viewed_at":"2026-09-10T10:00:00+00:00","completed_at":""},
            {"material_id":"m2","username":"s1","progress":90,"completed":1,"last_viewed_at":"2026-09-11T10:00:00+00:00","completed_at":"2026-09-11T10:00:00+00:00"},
        ]
        legacy_material_rows = [{"emp_id":"E001","material_id":"m3","completed_at":"2026-09-12T10:00:00+00:00"}]
        exam_rows = [
            {"id":"e1","emp_id":"E001","quiz_title":"Exam 1","score":90,"status":"completed","review_status":"completed","passing_score":80,"training_area":"pgy","group_key":"grpHema","created_at":"2026-09-13T10:00:00+00:00"},
            {"id":"e2","emp_id":"E001","quiz_title":"Essay","score":0,"status":"completed","review_status":"pending","passing_score":80,"training_area":"pgy","group_key":"grpHema","created_at":"2026-09-14T10:00:00+00:00"},
        ]
        assignments = [
            {"id":"a1","learner_username":"s1","status":"finalized","updated_at":"2026-09-15T08:00:00+00:00"},
            {"id":"a2","learner_username":"s1","status":"assigned","updated_at":"2026-09-15T09:00:00+00:00"},
        ]
        assessments = [{"id":"p1","assessment_type":"mini_cex","emp_id":"E001","overall_score":4.5,"status":"completed","assessment_date":"2026-09-15","created_at":"2026-09-15T10:00:00+00:00"}]
        data = analytics.project_analytics({"kind":"self","roles":["student"],"group":"grpHema"}, [LEARNER], learning_rows, legacy_material_rows, exam_rows, assignments, assessments, now=NOW)
        row = data["learners"][0]
        self.assertEqual(row["materials"]["tracked"], 3)
        self.assertEqual(row["materials"]["completed"], 2)
        self.assertEqual(row["exams"]["attempts"], 2)
        self.assertEqual(row["exams"]["pendingReview"], 1)
        self.assertEqual(row["exams"]["averageScore"], 90.0)
        self.assertEqual(row["pgy"]["completionRate"], 50.0)
        self.assertEqual(row["pgy"]["assessmentAverage"], 4.5)
        self.assertEqual(data["summary"]["examPassRate"], 100.0)
        self.assertEqual(data["interpretation"], "descriptive_existing_records_only")
        self.assertNotIn("mastery", data)
        september = next(item for item in data["timeline"] if item["month"] == "2026-09")
        self.assertGreaterEqual(september["materials"], 2)
        self.assertEqual(september["exams"], 2)
        self.assertEqual(september["pgy"], 1)
        self.assertEqual(september["assessments"], 1)


class CommandCenterM2M3RouteTests(unittest.TestCase):
    def make_client(self, user):
        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY="test")
        base = SimpleNamespace(app=app, _current_user=lambda: user)
        register_training_command_center(base)
        return app.test_client()

    def test_online_user_gets_no_pgy_matrix(self):
        client = self.make_client({"username":"online","role":"student","pgyLearner":False})
        with patch("teacher_app.command_center.routes.competency.build_competency_matrix") as matrix:
            response = client.get('/api/training-command-center/pgy-matrix')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["audience"], "online")
        self.assertEqual(response.get_json()["learners"], [])
        matrix.assert_not_called()

    def test_pgy_matrix_and_analytics_routes_are_get_only(self):
        client = self.make_client({"username":"s1","role":"student","pgyLearner":True})
        with patch("teacher_app.command_center.routes.competency.build_competency_matrix", return_value={"learners":[],"summary":{}}):
            response = client.get('/api/training-command-center/pgy-matrix')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["pgyLearner"])
        self.assertEqual(client.post('/api/training-command-center/pgy-matrix').status_code, 405)
        with patch("teacher_app.command_center.routes.analytics.build_learning_analytics", return_value={"learners":[],"summary":{},"timeline":[]}):
            response = client.get('/api/training-command-center/learning-analytics')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["audience"], "pgy")
        self.assertEqual(client.post('/api/training-command-center/learning-analytics').status_code, 405)

    def test_online_analytics_response_removes_pgy_projection(self):
        client = self.make_client({"username":"online","role":"student","pgyLearner":False})
        raw={"summary":{"materialsTracked":1,"pgyAssignments":3,"pgyCompletionRate":50},"learners":[{"name":"A","pgy":{"assignments":3}}],"timeline":[{"month":"2026-09","materials":1,"pgy":2,"assessments":1}]}
        with patch("teacher_app.command_center.routes.analytics.build_learning_analytics", return_value=raw):
            data=client.get('/api/training-command-center/learning-analytics').get_json()
        self.assertNotIn('pgyAssignments', data['summary'])
        self.assertNotIn('pgy', data['learners'][0])
        self.assertNotIn('pgy', data['timeline'][0])


class CommandCenterM2M3FrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix_ui = ROOT.joinpath('static','pgy-competency-matrix-71.js').read_text(encoding='utf-8')
        cls.analytics_ui = ROOT.joinpath('static','learning-analytics-71.js').read_text(encoding='utf-8')
        cls.frontend = ROOT.joinpath('teacher_app','frontend','assets.py').read_text(encoding='utf-8')
        cls.workflow = ROOT.joinpath('.github','workflows','phase3-pgy-checks.yml').read_text(encoding='utf-8')
        cls.coverage = ROOT.joinpath('RC_FEATURE_UI_COVERAGE_MATRIX.md').read_text(encoding='utf-8')

    def test_m2_switches_between_pgy_and_online_progress(self):
        self.assertIn('PGY 能力矩陣／訓練進度', self.matrix_ui)
        self.assertIn('線上訓練進度', self.matrix_ui)
        self.assertIn('p?.pgyLearner', self.matrix_ui)
        self.assertIn('/api/dashboard/me?', self.matrix_ui)
        self.assertIn('/api/training-command-center/pgy-matrix', self.matrix_ui)
        self.assertIn("if (section) section.classList.add('hidden');", self.matrix_ui)
        self.assertEqual(self.matrix_ui.count("if (section) section.classList.remove('hidden');"), 1)
        for mutation in ("method: 'POST'", "method: 'PATCH'", "method: 'DELETE'"):
            self.assertNotIn(mutation, self.matrix_ui)

    def test_m3_is_compact_inside_course_center_and_uses_home_dashboard_source(self):
        self.assertIn("document.querySelector('#course-overview > .edu-card')", self.analytics_ui)
        self.assertIn('📊 學習摘要', self.analytics_ui)
        self.assertIn('/api/dashboard/me?', self.analytics_ui)
        self.assertIn('materialsCompleted', self.analytics_ui)
        self.assertIn('materialsTotal', self.analytics_ui)
        self.assertIn('p?.pgyLearner', self.analytics_ui)
        self.assertIn('<details id="learning-analytics-detail-71"', self.analytics_ui)
        for mutation in ("method: 'POST'", "method: 'PATCH'", "method: 'DELETE'"):
            self.assertNotIn(mutation, self.analytics_ui)

    def test_m1_m2_m3_assets_load_in_order_and_are_syntax_checked(self):
        self.assertLess(self.frontend.index('/training-command-center-71.js'), self.frontend.index('/pgy-competency-matrix-71.js'))
        self.assertLess(self.frontend.index('/pgy-competency-matrix-71.js'), self.frontend.index('/learning-analytics-71.js'))
        self.assertIn("find static -type f -name '*.js'", self.workflow)

    def test_rc_matrix_records_audience_split_and_compact_m3(self):
        self.assertIn('PGY competency matrix / online training progress (7.1 M2)', self.coverage)
        self.assertIn('Learning Analytics (7.1 M3)', self.coverage)
        self.assertIn('compact', self.coverage.lower())
        self.assertIn('pgy_learner', self.coverage)


if __name__ == '__main__':
    unittest.main()
