import unittest
from pathlib import Path

from teacher_app.materials import ai_presentation_repository as repository
from teacher_app.materials import ai_presentation_runtime as runtime


ROOT=Path(__file__).parents[1]


class F5PresentationProvenanceTests(unittest.TestCase):
    def test_source_context_captures_material_version(self):
        draft={
            "id":"d1","sourceJobId":"j1","sourceChunks":[{"chunkId":"c1"}],
            "provider":"local","model":"m1","approvedBy":"teacher","approvedAt":"2026-10-04",
        }
        source={"id":"m1","currentVersion":7}
        data=runtime._source_context(draft,source,template_id="t1",revision_number=3)
        self.assertEqual(data["sourceMaterialVersion"],7)
        self.assertEqual(data["revisionNumber"],3)

    def test_sanitizer_keeps_bounded_source_version(self):
        data=repository.sanitize_provenance({"sourceMaterialId":"m1","sourceMaterialVersion":9})
        self.assertEqual(data["sourceMaterialVersion"],9)

    def test_teacher_ui_uses_human_readable_trace(self):
        source=ROOT.joinpath("static","teacher-ai-presentation-1016.js").read_text(encoding="utf-8")
        self.assertIn("來源教材版本",source)
        self.assertIn("來源教材之後已有新版",source)
        self.assertIn("RAG 來源片段",source)
        self.assertNotIn("JSON.stringify(data.provenance",source)


if __name__=="__main__":
    unittest.main()
