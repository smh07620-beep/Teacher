"""教材「更換組別」（2026-10-13）：生化組的教材要能移到鏡檢組課程使用。

前端：只有教學管理者／系統管理者看得到「更換組別」，用下拉選單，不用輸入代碼。
伺服器：既有 PATCH /api/slides/<id> 已用 scoped 規則擋住組長／臨床教師把教材移到別組。
"""
import unittest
from pathlib import Path
from unittest import mock

from flask import Flask, request

from teacher_app.auth import rbac_legacy_adapter
from teacher_app.common import scope_filter

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "static" / "admin-course-material.js").read_text(encoding="utf-8")


class MaterialGroupMoveFrontendTests(unittest.TestCase):
    def test_menu_item_is_only_rendered_for_cross_group_managers(self):
        self.assertIn("function canMoveMaterialGroup()", SOURCE)
        self.assertIn("function adminMaterialGroupMoveButton(m)", SOURCE)
        self.assertIn("if(!canMoveMaterialGroup())return '';", SOURCE)
        body = SOURCE[SOURCE.index("function canMoveMaterialGroup()"):]
        body = body[:body.index("function ensureMaterialGroupMoveDialog")]
        for token in ("system_admin", "education_admin", "education.cross_group.manage"):
            self.assertIn(token, body)

    def test_dialog_uses_a_dropdown_and_patches_group_and_area_only(self):
        self.assertIn("data-group-move-select", SOURCE)
        self.assertIn("body:JSON.stringify({group,area:ctx.area})", SOURCE)
        self.assertIn("method:'PATCH'", SOURCE[SOURCE.index("function ensureMaterialGroupMoveDialog"):])

    def test_button_is_visible_on_every_row_including_course_materials(self):
        row = SOURCE[SOURCE.index("function adminHubMaterialRow"):SOURCE.index("function ensureMaterialPurgeDialog")]
        self.assertEqual(row.count("${adminMaterialGroupMoveButton(m)}"), 2)
        self.assertNotIn("data-material-group-move", row)
        body = SOURCE[SOURCE.index("function openMaterialGroupMoveDialog"):]
        body = body[:body.index("function bindMaterialGroupMoveControls")]
        self.assertNotIn("if(material.courseId)return alert(", body)

    def test_controls_are_bound_when_the_hub_paints(self):
        paint = SOURCE[SOURCE.index("function paintAdminCourseMaterialHub"):]
        self.assertIn("bindMaterialGroupMoveControls(box);", paint[:400])

    def test_material_pointing_at_a_course_in_another_group_is_not_hidden(self):
        paint = SOURCE[SOURCE.index("function paintAdminCourseMaterialHub"):]
        self.assertIn("!m.courseId||!hubContext.courses.has(String(m.courseId))", paint)
        row = SOURCE[SOURCE.index("function adminHubMaterialRow"):SOURCE.index("function ensureMaterialPurgeDialog")]
        self.assertIn("m.courseId&&hubContext.courses.has(String(m.courseId))", row)

    def test_no_inline_event_handlers_for_csp(self):
        block = SOURCE[SOURCE.index("function ensureMaterialGroupMoveDialog"):SOURCE.index("function bindMaterialCourseLinkControls")]
        self.assertNotIn("onclick=", block)
        self.assertNotIn("onchange=", block)


class MaterialGroupMoveServerGuardTests(unittest.TestCase):
    def test_update_material_endpoint_stays_group_scoped(self):
        self.assertEqual(
            rbac_legacy_adapter.LEGACY_ENDPOINT_POLICIES["api_update_slide"],
            ("material.manage", "scoped"),
        )

    def test_request_groups_covers_both_the_current_and_the_requested_group(self):
        # A group-scoped actor is only allowed when this set is exactly {own group}, so a
        # move out of (or into) another group is rejected with 403.
        app = Flask(__name__)
        with app.test_request_context("/api/slides/m1", method="PATCH", json={"group": "grpMicro"}):
            request.view_args = {"slide_id": "m1"}
            with mock.patch.object(scope_filter.material_repository, "get_material", return_value={"group": "grpBio"}):
                groups = scope_filter.request_groups()
        self.assertEqual(groups, {"grpBio", "grpMicro"})


if __name__ == "__main__":
    unittest.main()
