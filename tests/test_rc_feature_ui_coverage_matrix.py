"""Release-candidate feature/UI coverage matrix contract."""
from pathlib import Path


ROOT = Path(__file__).parents[1]
MATRIX = ROOT.joinpath("RC_FEATURE_UI_COVERAGE_MATRIX.md")


def test_rc_matrix_exists_and_has_required_columns():
    source = MATRIX.read_text(encoding="utf-8")
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
        assert marker in source


def test_rc_matrix_covers_current_formal_product_surfaces():
    source = MATRIX.read_text(encoding="utf-8")
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
        assert marker in source


def test_rc_matrix_requires_ui_or_internal_classification():
    source = MATRIX.read_text(encoding="utf-8")
    assert "A backend feature without a normal UI entry must not be marked `Usable`" in source
    assert "explicitly classified as `Internal`" in source
    assert "New product work must update this" in source


def test_internal_and_deferred_surfaces_are_explicit():
    source = MATRIX.read_text(encoding="utf-8")
    for marker in (
        "Raw provider credentials / SDK clients",
        "Worker token / local worker protocol secret",
        "Background media conversion primitives",
        "Storage/provider ownership extraction",
        "Internal",
        "Deferred",
        "Compatibility",
    ):
        assert marker in source
