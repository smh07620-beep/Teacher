import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from pgy_frontend import ASSET_MANIFEST
from teacher_app.command_center import progress
from teacher_app.command_center.routes import register_training_command_center


ROOT = Path(__file__).parents[1]


class LearningProgressConvergence1025Tests(unittest.TestCase):
    def test_online_progress_uses_dashboard_summary_as_single_learning_source(self):
        user = {"username":"s1","name":"學員","empId":"E1","role":"student","pgyLearner":False}
        dashboard = {
            "progressPercent": 67,
            "materialsCompleted": 2,
            "materialsTotal": 3,
            "examsPassed": 1,
            "examsTotal": 2,
            "activeCourses": 1,
            "scopeSource": "assignments",
        }
        with patch.object(progress.audience, "current_profile", return_value={"audience":"online","pgyLearner":False}), \
             patch.object(progress.dashboard_service, "dashboard_summary", return_value=dashboard), \
             patch.object(progress.competency, "build_competency_matrix") as matrix:
            data = progress.build_progress(user)
        self.assertEqual(data["online"]["percent"], 67)
        self.assertEqual(data["online"]["materialsCompleted"], 2)
        self.assertIsNone(data["pgy"])
        matrix.assert_not_called()
        self.assertEqual(data["interpretation"], "separate_online_and_pgy_progress_sources")

    def test_pgy_progress_is_separate_from_online_learning_percent(self):
        user = {"username":"p1","name":"PGY","empId":"P1","role":"student","pgyLearner":True}
        with patch.object(progress.audience, "current_profile", return_value={"audience":"pgy","pgyLearner":True}), \
             patch.object(progress.dashboard_service, "dashboard_summary", return_value={"progressPercent":75}), \
             patch.object(progress.competency, "build_competency_matrix", return_value={"summary":{
                 "assignmentCompletionPercent":50.0,"assignmentsCompleted":1,"assignments":2,
                 "assignmentsOverdue":1,"averageAssessmentScore":4.5,
             }}):
            data = progress.build_progress(user)
        self.assertEqual(data["online"]["percent"], 75)
        self.assertEqual(data["pgy"]["percent"], 50.0)
        self.assertEqual(data["pgy"]["assignmentsOverdue"], 1)

    def test_progress_route_is_read_only(self):
        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY="test")
        class Owner:
            def __init__(self, app): self.app = app
            def _current_user(self): return {"username":"s","name":"S","empId":"E","role":"student"}
        register_training_command_center(Owner(app))
        client = app.test_client()
        expected={"audience":"online","pgyLearner":False,"online":{"percent":0},"pgy":None}
        with patch("teacher_app.command_center.routes.progress.build_progress", return_value=expected):
            response=client.get('/api/training-command-center/progress')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.get_json(),expected)
        self.assertEqual(client.post('/api/training-command-center/progress').status_code,405)

    def test_frontend_convergence_is_loaded_on_portal_and_system(self):
        source=ROOT.joinpath('static','learning-progress-convergence-1025.js').read_text(encoding='utf-8')
        for marker in (
            '/api/training-command-center/progress',
            'v561-progress-percent',
            'training-progress-summary-71',
            'learning-analytics-stats-71',
            'pgy-matrix-stats-71',
            "dataset.progressSource='training-command-center'",
        ):
            self.assertIn(marker,source)
        self.assertIn('/learning-progress-convergence-1025.js', ASSET_MANIFEST['portal']['body'])
        self.assertIn('/learning-progress-convergence-1025.js', ASSET_MANIFEST['system']['body'])
        self.assertNotIn('X-Admin-Key',source)
        self.assertNotIn('getAdminKey',source)


if __name__ == '__main__':
    unittest.main()
