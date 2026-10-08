"""Course overview: the material 更多 menu is complete and never clipped."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


def read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


class CourseHubMaterialMenuTests(unittest.TestCase):
    def test_menu_has_audience_index_and_atlas_actions(self):
        js = read("static", "admin-course-material.js")
        row = js[js.index("function adminHubMaterialRow"):]
        for marker in (
            'data-material-audience="',
            "rebuildMaterialIndex('${m.id}')",
            "openAdminMaterialAtlasImport('${m.id}')",
            "viewMaterialVersions('${m.id}')",
            "deleteAdminMaterial('${m.id}')",
        ):
            self.assertIn(marker, row)

    def test_course_card_does_not_clip_the_hanging_menu(self):
        js = read("static", "admin-course-material.js")
        card = re.search(r'<details data-course-id="[^>]*class="([^"]*)"', js).group(1)
        self.assertNotIn("overflow-hidden", card)
        css = read("static", "admin.css")
        self.assertIn("details[data-course-id][open] > :last-child", css)
        self.assertIn("[data-material-more][open] { position: relative; z-index: 30; }", css)

    def test_restricted_material_shows_a_hint_in_the_overview(self):
        js = read("static", "admin-course-material.js")
        self.assertIn("本組限定：其他組別看不到（更多 → 設定可見範圍）", js)

    def test_audience_editor_is_reachable_from_the_overview_menu(self):
        audience = read("static", "content-audience-1014.js")
        self.assertIn("[data-material-audience]", audience)
        self.assertIn("editMaterialAudience(id, item)", audience)

    def test_advanced_list_no_longer_pretends_to_be_the_daily_tool(self):
        html = read("static", "system.html")
        self.assertIn("都已整合在上方各課程的「更多」", html)


if __name__ == "__main__":
    unittest.main()
