import re, unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "teacher_app/assessments/service.py"


class ExamDraftIdempotentTests(unittest.TestCase):
    def test_course_bound_create_reuses_unpublished_draft(self):
        text = SRC.read_text(encoding="utf-8")
        body = text[text.index("def create_category"):text.index("def update_category")]
        self.assertIn("repository.list_categories(group, area, include_inactive=True)", body)
        self.assertIn('str(existing.get("courseId") or "") == course_id', body)
        self.assertLess(body.index("return existing"), body.index("repository.create_category("))


if __name__ == "__main__":
    unittest.main()
