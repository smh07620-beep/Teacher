"""A course assigned individually from another group must open WITH its materials (2026-10-15).

The server re-labels another group's materials with the learner's own group (the real
owner stays in ownerGroup) while the assigned course keeps its owner group, so the learner
screens must match materials through ownerGroup and keep assignedFromGroup courses/exams.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class LearnerCrossGroupAssignedCourseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.teaching = (ROOT / "static" / "teaching.js").read_text(encoding="utf-8")
        cls.learner = (ROOT / "static" / "system-learner.js").read_text(encoding="utf-8")
        cls.audience = (ROOT / "teacher_app" / "common" / "content_audience.py").read_text(encoding="utf-8")

    def test_server_still_relabels_shared_materials_and_keeps_owner(self):
        self.assertIn('enriched["group"] = user_group', self.audience)
        self.assertIn('"ownerGroup": str(meta.get("ownerGroup")', self.audience)

    def test_course_overview_matches_materials_through_owner_group(self):
        self.assertIn("m.ownerGroup === currentGroupKey", self.teaching)
        self.assertIn("m.ownerGroup===currentGroupKey", self.learner)

    def test_assigned_from_other_group_courses_and_exams_are_kept(self):
        self.assertIn("c.assignedFromGroup", self.teaching)
        self.assertIn("q.assignedFromGroup", self.teaching)
        self.assertIn("c.assignedFromGroup", self.learner)
        self.assertIn("q.assignedFromGroup", self.learner)

    def test_flat_material_list_also_uses_owner_group(self):
        self.assertIn("s.ownerGroup === currentGroupKey", self.learner)


if __name__ == "__main__":
    unittest.main()
