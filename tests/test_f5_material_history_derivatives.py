import unittest
from pathlib import Path
from unittest.mock import patch

from teacher_app.materials import service


ROOT=Path(__file__).parents[1]


class F5MaterialHistoryDerivativeTests(unittest.TestCase):
    def test_material_version_service_groups_derivatives_by_version(self):
        versions=[
            {"materialId":"m1","version":2,"changeReason":"update"},
            {"materialId":"m1","version":1,"changeReason":"baseline"},
        ]
        derivatives=[
            {"materialId":"m1","materialVersion":2,"type":"presentation","derivativeId":"p1"},
            {"materialId":"m1","materialVersion":2,"type":"video","derivativeId":"v1"},
        ]
        with patch.object(service.repository,"get_material",return_value={"id":"m1"}), \
             patch.object(service.repository,"list_material_versions",return_value=versions), \
             patch.object(service.derivative_repository,"list_for_material",return_value=derivatives):
            rows=service.list_material_versions("m1")
        self.assertEqual(len(rows[0]["derivatives"]),2)
        self.assertEqual(rows[1]["derivatives"],[])

    def test_material_history_ui_names_ai_derivatives(self):
        source=ROOT.joinpath("static","admin-material-upload.js").read_text(encoding="utf-8")
        self.assertIn("衍生內容：",source)
        self.assertIn("AI 教學影片",source)
        self.assertIn("AI PowerPoint",source)

    def test_publish_ui_reports_attached_material_version(self):
        ppt=ROOT.joinpath("static","teacher-ai-presentation-1016.js").read_text(encoding="utf-8")
        video=ROOT.joinpath("static","teacher-ai-video-1015.js").read_text(encoding="utf-8")
        self.assertIn("materialDerivative?.materialVersion",ppt)
        self.assertIn("materialDerivative?.materialVersion",video)
        self.assertIn("AI VIDEO · F5",video)


if __name__=="__main__":
    unittest.main()
