"""Release-candidate feature/UI coverage matrix contract."""
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
MATRIX = ROOT.joinpath("RC_FEATURE_UI_COVERAGE_MATRIX.md")


class RcFeatureUiCoverageMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MATRIX.read_text(encoding="utf-8")

    def test_rc_matrix_exists_and_has_required_columns(self):
        for marker in (
            "# RC Feature / UI Coverage Matrix",
            "Backend / runtime owner",
            "API / contract",
            "UI / caller",
            "RBAC / scope",
            "Regression coverage",
            "Status",
            "## Release gate",
        ):
            self.assertIn(marker, self.source)

    def test_rc_matrix_covers_current_formal_product_surfaces(self):
        for marker in (
            "Course Wizard",
            "Material catalog / metadata",
            "Assessment configuration / review / publication",
            "Question Bank 2.0",
            "AI-assisted question generation",
            "Exam blueprint snapshots",
            "Item analytics",
            "PGY assignment workflow",
            "PGY signing / countersign / finalize",
            "Atlas teaching resource",
            "DOCX → Atlas import",
            "Worker / job operational status",
            "Audit / read-only oversight",
            "Backup / restore maintenance",
        ):
            self.assertIn(marker, self.source)

    def test_rc_matrix_requires_ui_or_internal_classification(self):
        self.assertIn(
            "A backend feature without a normal UI entry must not be marked `Usable`",
            self.source,
        )
        self.assertIn("explicitly classified as `Internal`", self.source)
        self.assertIn("New product work must update this", self.source)

    def test_internal_and_deferred_surfaces_are_explicit(self):
        for marker in (
            "Raw provider credentials / SDK clients",
            "Worker token / local worker protocol secret",
            "Background media conversion primitives",
            "Storage/provider ownership extraction",
            "Internal",
            "Deferred",
            "Compatibility",
        ):
            self.assertIn(marker, self.source)


if __name__ == "__main__":
    unittest.main()
