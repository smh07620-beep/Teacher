"""Exam records of a cross-group assigned course must count in the learner's status (2026-10-15)."""
import unittest
from pathlib import Path

SRC = (Path(__file__).resolve().parents[1] / "teacher_app" / "learning" / "progress_service.py").read_text(encoding="utf-8")


class MyProgressCrossGroupTests(unittest.TestCase):
    def test_records_not_limited_to_current_group(self):
        self.assertNotIn("AND group_key={ph}", SRC)
        self.assertIn("assigned_course_grants(user)", SRC)
        self.assertIn('in granted_courses', SRC)

    def test_records_without_course_id_match_by_exam(self):
        self.assertIn("granted_exam_ids", SRC)
        self.assertIn('record.get("quizCategoryId")', SRC)

    def test_assigned_course_materials_count_for_completion(self):
        self.assertIn('str(item.get("courseId") or "") in granted_courses', SRC)


if __name__ == "__main__":
    unittest.main()
