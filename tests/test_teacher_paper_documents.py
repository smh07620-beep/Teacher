from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TeacherPaperDocumentWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = (ROOT / "static" / "admin-results-workspace.js").read_text(encoding="utf-8")
        cls.export = (ROOT / "static" / "admin-results-export.js").read_text(encoding="utf-8")

    def test_teacher_workspace_exposes_paper_document_mode(self):
        for marker in (
            "teacher-mode-documents",
            "📄 紙本文件與匯出",
            "Word · 列印 · 簽核 · 歸檔",
            "列印前留存檢核",
            "文件可追溯欄位",
            "state.resultMode === 'documents'",
        ):
            self.assertIn(marker, self.workspace)

    def test_paper_document_mode_keeps_results_as_source_of_truth(self):
        self.assertIn("window.switchAdminSection?.('results', true)", self.workspace)
        self.assertIn("下方列表就是正式考核紀錄來源", self.workspace)
        self.assertIn("不要重新手打姓名、工號、分數或評核者資料", self.workspace)
        self.assertNotIn("/api/", self.workspace)

    def test_word_payload_has_paper_retention_metadata(self):
        for marker in (
            "documentTitle",
            "documentReference",
            "documentVersion",
            "assessmentDate",
            "exportedAt",
            "exportedBy",
            "paperStatus",
            "examineeSignature",
            "evaluatorSignature",
            "reviewSignature",
            "signatureDate",
            "archiveNumber",
            "archiveNote",
        ):
            self.assertIn(marker, self.export)

    def test_existing_docx_contract_remains_backward_compatible(self):
        self.assertIn("window.buildRecordDocPayload", self.export)
        self.assertIn("window.exportWithServerTemplate", self.export)
        self.assertIn("window.exportRecordToWord", self.export)
        self.assertIn("附件1.${filenamePart}.docx", self.export)
        self.assertIn("...paperMeta", self.export)


if __name__ == "__main__":
    unittest.main()
