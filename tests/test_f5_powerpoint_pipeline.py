import unittest
from pathlib import Path


ROOT=Path(__file__).parents[1]


class F5PowerPointPipelineTests(unittest.TestCase):
    def test_status_contract_exposes_f5_workflow(self):
        source=ROOT.joinpath("teacher_app","materials","ai_presentation_routes.py").read_text(encoding="utf-8")
        self.assertIn('"productPhase": "F5"',source)
        self.assertIn('"videoHandoff": True',source)
        self.assertIn('"artifact": "shared-durable-pptx"',source)
        self.assertIn('_ai_worker_status()',source)
        self.assertIn('"ready": ready',source)
        self.assertIn('_ai_worker_online_error()',source)

    def test_teacher_ui_presents_one_five_step_pipeline(self):
        source=ROOT.joinpath("static","teacher-ai-presentation-1016.js").read_text(encoding="utf-8")
        self.assertIn("AI POWERPOINT · F5",source)
        self.assertIn("teacher-ai-presentation-flow-1016",source)
        self.assertIn("AI Worker 產生 PPTX",source)
        self.assertIn("發布或接續影片",source)
        self.assertIn("serviceReady",source)
        self.assertIn("等待 AI Worker 回報",source)


if __name__=="__main__":
    unittest.main()
