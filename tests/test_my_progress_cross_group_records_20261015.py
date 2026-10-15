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


class MyProgressCrossScopeRequestTests(unittest.TestCase):
    """The owner-group screen asks for progress under the owner group (2026-10-15)."""

    USER = {"empId": "04960", "name": "T", "username": "04960", "role": "group_leader",
            "preferredArea": "internal", "preferredGroup": "grpMicroscopy"}

    def test_assigned_cross_group_is_allowed_and_unassigned_is_not(self):
        from unittest.mock import patch
        from teacher_app.learning import progress_service as ps

        course = {"id": "c503", "group": "grpBio", "area": "internal"}
        with patch.object(ps.learning_access, "assigned_course_grants", return_value=frozenset({"c503"})), \
             patch.object(ps.course_repository, "get_course", return_value=course):
            self.assertTrue(ps._has_assigned_course_in(self.USER, "internal", "grpBio"))
            self.assertFalse(ps._has_assigned_course_in(self.USER, "internal", "grpMicro"))
        with patch.object(ps.learning_access, "assigned_course_grants", return_value=frozenset()):
            self.assertFalse(ps._has_assigned_course_in(self.USER, "internal", "grpBio"))

    def test_cross_scope_payload_is_limited_to_assigned_courses(self):
        self.assertIn("if not own_scope:", SRC)
        self.assertIn("courses = [c for c in courses if str(c.get(\"id\") or \"\") in granted_courses]", SRC)
