import unittest
import zipfile
from pathlib import Path

from teacher_app.frontend.assets import ASSET_MANIFEST, STUDENT_LEAN_EXCLUDE

ROOT = Path(__file__).resolve().parents[1]


class ResultsBatchExport1106Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / "static" / "admin-results-batch-export-1106.js").read_text(encoding="utf-8")
        cls.data = (ROOT / "static" / "admin-results-data.js").read_text(encoding="utf-8")

    def test_script_loaded_for_staff_only(self):
        self.assertIn("/admin-results-batch-export-1106.js", ASSET_MANIFEST["system"]["body"])
        self.assertIn("/admin-results-batch-export-1106.js", STUDENT_LEAN_EXCLUDE)

    def test_exports_follow_on_screen_filters(self):
        self.assertIn("window.adminResultsVisibleRecords", self.data)
        self.assertIn("visibleResultRecords(records)", self.data)
        self.assertIn("adminResultsVisibleRecords()", self.js)

    def test_word_grouped_per_person(self):
        self.assertIn("--匯出考卷", self.js)
        self.assertIn("buildRecordDocPayload", self.js)

    def test_l03_valid_date_is_course_end_plus_one_year_and_note_blank(self):
        self.assertIn("plusOneYear(endDate)", self.js)
        self.assertIn("note: ''", self.js)
        self.assertIn("年${groupName(", self.js)

    def test_l03_template_has_tags(self):
        path = ROOT / "static" / "templates" / "QP15-L03.docx"
        xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
        for tag in ("{#exams}", "{/exams}", "{title}", "{item}", "{examDate}", "{#rows}", "{validUntil}", "{/rows}", "QP15-L03"):
            self.assertIn(tag, xml)
        self.assertIn("headerReference", xml)


if __name__ == "__main__":
    unittest.main()


class Qp15L03UploadUiTests(unittest.TestCase):
    def test_upload_converts_in_browser_and_falls_back_to_builtin(self):
        js = (ROOT / "static" / "admin-results-batch-export-1106.js").read_text(encoding="utf-8")
        self.assertIn("window.buildQp15L03Template", js)
        self.assertIn("/api/doc-templates/${L03_KEY}/download", js)
        self.assertIn("L03_TEMPLATE_URL", js)
        self.assertIn("改回內建版", js)


class WordLibsFallbackTests(unittest.TestCase):
    def test_self_hosted_word_libs_loaded_when_cdn_blocked(self):
        js = (ROOT / "static" / "admin-results-batch-export-1106.js").read_text(encoding="utf-8")
        self.assertIn("ensureWordLibs", js)
        for name in ("pizzip-3.1.4.min.js", "docxtemplater-3.37.11.js", "FileSaver-2.0.5.min.js"):
            self.assertTrue((ROOT / "static" / "vendor" / name).exists())
            self.assertIn(f"/vendor/{name}", js)


class ResultsGroupedByPersonTests(unittest.TestCase):
    def test_one_row_per_person_with_folded_exams_and_no_role_banner(self):
        js = (ROOT / "static" / "admin-results-data.js").read_text(encoding="utf-8")
        self.assertIn("data-person-toggle", js)
        self.assertIn("data-person-exam", js)
        self.assertIn("匯出此人考卷", js)
        self.assertNotIn("人員別：", js)


class PassStandardTagTests(unittest.TestCase):
    def test_word_payload_fills_pass_standard_tag(self):
        js = (ROOT / "static" / "admin-results-export.js").read_text(encoding="utf-8")
        self.assertEqual(js.count("passStandard:passingScore"), 2)
