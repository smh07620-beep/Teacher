"""2026-10-09: 「僅供老師製作使用」教材：學員在伺服器端看不到，也不列入完成條件。"""
import unittest
from pathlib import Path

from teacher_app.common import content_audience
from teacher_app.learning import access as learning_access
from teacher_app.learning.completion import evaluate_course_completion

ROOT = Path(__file__).resolve().parents[1]


def person(role, group="grpBio"):
    return {"username": role + group, "role": role, "roles": [role], "preferredGroup": group,
            "preferredArea": "internal"}


META = {"ownerGroup": "grpBio", "audienceScope": "source_only", "audienceGroups": [], "courseId": "c1"}
ITEM = {"id": "m1", "group": "grpBio", "area": "internal", "courseId": "c1", "audienceScope": "source_only"}


class SourceOnlyVisibilityTests(unittest.TestCase):
    def test_student_never_sees_source_only_material(self):
        self.assertFalse(content_audience.visible_to_user(person("student"), META))
        self.assertFalse(learning_access.can_access_learning_item(person("student"), ITEM))

    def test_same_group_teacher_and_leader_can_use_it(self):
        for role in ("clinical_teacher", "group_leader"):
            self.assertTrue(content_audience.visible_to_user(person(role), META), role)
            self.assertTrue(learning_access.can_access_learning_item(person(role), ITEM), role)

    def test_other_group_teacher_cannot(self):
        other = person("group_leader", "grpHema")
        self.assertFalse(content_audience.visible_to_user(other, META))
        self.assertFalse(learning_access.can_access_learning_item(other, ITEM))

    def test_cross_group_managers_can(self):
        for role in ("education_admin", "system_admin"):
            self.assertTrue(content_audience.visible_to_user(person(role, "grpHema"), META), role)
            self.assertTrue(learning_access.can_access_learning_item(person(role, "grpHema"), ITEM), role)

    def test_other_scopes_are_unchanged(self):
        shared = {**META, "audienceScope": "all_staff"}
        self.assertTrue(content_audience.visible_to_user(person("student", "grpHema"), shared))
        self.assertIn("source_only", content_audience.AUDIENCE_SCOPES)


class SourceOnlyCompletionTests(unittest.TestCase):
    def test_source_only_material_is_not_required_for_completion(self):
        materials = [
            {"id": "visible", "audienceScope": "all_staff"},
            {"id": "source", "audienceScope": "source_only"},
        ]
        result = evaluate_course_completion(materials=materials, exams=[], completed_material_ids={"visible"}, passed_exam_ids=set())
        self.assertEqual(result["materialsTotal"], 1)
        self.assertTrue(result["completed"])


class SourceOnlyWizardTests(unittest.TestCase):
    def test_wizard_checkbox_and_apply(self):
        wiz = ROOT.joinpath("static", "course-wizard-681.js").read_text(encoding="utf-8")
        self.assertIn('id="cw681-source-only"', wiz)
        self.assertIn("只當 AI 出題／製作來源，不顯示給學員", wiz)
        self.assertIn("async function applySourceOnlyAudience(materialIds)", wiz)
        self.assertIn("audienceScope:'source_only'", wiz)
        self.assertIn("設為僅供製作", wiz)


if __name__ == "__main__":
    unittest.main()
