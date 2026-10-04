import unittest
from pathlib import Path


ROOT=Path(__file__).parents[1]


class F5DerivativePublishIntegrationTests(unittest.TestCase):
    def test_presentation_publish_records_material_derivative_before_status_publish(self):
        source=ROOT.joinpath("teacher_app","materials","ai_presentation_routes.py").read_text(encoding="utf-8")
        ledger=source.index("derivative_repository.record_publication")
        status=source.index('status="published"',ledger)
        self.assertLess(ledger,status)
        self.assertIn('"materialDerivative":derivative',source)
        self.assertIn('derivative_type="presentation"',source)

    def test_video_publish_resolves_canonical_material_and_records_derivative(self):
        source=ROOT.joinpath("teacher_app","materials","ai_video_routes.py").read_text(encoding="utf-8")
        self.assertIn("get_publication_for_presentation",source)
        self.assertIn('or presentation.get("materialId")',source)
        self.assertIn('derivative_type="video"',source)
        self.assertIn('"materialDerivative": derivative',source)

    def test_presentation_repository_can_resolve_explicit_publication_material(self):
        source=ROOT.joinpath("teacher_app","materials","ai_presentation_repository.py").read_text(encoding="utf-8")
        self.assertIn("def get_publication_for_presentation",source)
        self.assertIn("ORDER BY created_at DESC LIMIT 1",source)


if __name__=="__main__":
    unittest.main()
