import tempfile
import unittest
import zipfile
from pathlib import Path

from teacher_app.materials.job_commit import _sanitize_conversion_warnings
from teacher_app.worker import office_fidelity as fid

SLIDE = (
    '<p:sld xmlns:a="a" xmlns:p="p"><a:r><a:rPr><a:latin typeface="Segoe UI Variable"/>'
    '<a:ea typeface="標楷體"/></a:rPr></a:r>'
    '<a:bodyPr><a:normAutofit fontScale="77500" lnSpcReduction="20000"/></a:bodyPr></p:sld>'
)
THEME = '<a:theme xmlns:a="a"><a:latin typeface="+mn-lt"/><a:latin typeface="Arial"/></a:theme>'


def make_pptx(directory, slide=SLIDE):
    path = Path(directory) / "deck.pptx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", slide)
        archive.writestr("ppt/theme/theme1.xml", THEME)
    return path


class OfficeFidelityTests(unittest.TestCase):
    def test_fonts_used_ignores_theme_placeholders_and_reads_named_fonts(self):
        with tempfile.TemporaryDirectory() as tmp:
            used = fid.fonts_used(make_pptx(tmp))
        self.assertEqual(used, {"Segoe UI Variable", "標楷體", "Arial"})

    def test_docx_fonts_are_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.docx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("word/document.xml", '<w:p><w:rFonts w:ascii="Calibri" w:eastAsia="微軟正黑體"/></w:p>')
            self.assertEqual(fid.fonts_used(path), {"Calibri", "微軟正黑體"})

    def test_missing_fonts_are_reported_case_insensitively_and_safe_fonts_skipped(self):
        installed = {"標楷體", "calibri"}
        self.assertEqual(
            fid.missing_fonts({"Segoe UI Variable", "標楷體", "CALIBRI", "Arial"}, installed),
            ["Segoe UI Variable"],
        )

    def test_unknown_font_inventory_reports_nothing_instead_of_guessing(self):
        self.assertEqual(fid.missing_fonts({"Anything"}, set()), [])

    def test_autofit_counts_only_slides_that_were_actually_shrunk(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(fid.autofit_slide_count(make_pptx(tmp)), 1)
            plain = make_pptx(tmp, SLIDE.replace('fontScale="77500"', 'fontScale="100000"'))
            self.assertEqual(fid.autofit_slide_count(plain), 0)

    def test_conversion_warnings_explain_cause_and_suggest_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            warnings = fid.conversion_warnings(make_pptx(tmp), installed={"標楷體", "arial"})
        codes = [item["code"] for item in warnings]
        self.assertEqual(codes, ["missing_fonts", "autofit_text", "suggest_pdf"])
        self.assertIn("Segoe UI Variable", warnings[0]["message"])
        self.assertIn("PDF", warnings[2]["message"])

    def test_clean_deck_produces_no_warnings(self):
        with tempfile.TemporaryDirectory() as tmp:
            clean = make_pptx(tmp, '<a:r><a:latin typeface="Arial"/></a:r>')
            self.assertEqual(fid.conversion_warnings(clean, installed={"arial"}), [])

    def test_corrupt_or_non_ooxml_files_never_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "broken.pptx"
            bad.write_bytes(b"not a zip")
            self.assertEqual(fid.conversion_warnings(bad, installed={"arial"}), [])
            self.assertEqual(fid.conversion_warnings(Path(tmp) / "missing.pptx", installed={"arial"}), [])

    def test_web_side_sanitizer_bounds_worker_supplied_warnings(self):
        meta = {
            "previewMode": "single_pdf",
            "conversionWarnings": [
                {"code": "missing_fonts", "message": "x" * 900, "fonts": ["a"]},
                {"code": "", "message": "no code"},
                "junk",
            ] + [{"code": f"c{i}", "message": "m"} for i in range(20)],
        }
        cleaned = _sanitize_conversion_warnings(meta)
        self.assertEqual(cleaned["previewMode"], "single_pdf")
        self.assertLessEqual(len(cleaned["conversionWarnings"]), 6)
        self.assertEqual(len(cleaned["conversionWarnings"][0]["message"]), 300)
        self.assertNotIn("fonts", cleaned["conversionWarnings"][0])
        self.assertNotIn("conversionWarnings", _sanitize_conversion_warnings({"conversionWarnings": "bad"}))


if __name__ == "__main__":
    unittest.main()
