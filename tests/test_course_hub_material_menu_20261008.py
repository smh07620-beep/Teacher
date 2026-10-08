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

    def test_the_duplicate_advanced_material_list_is_gone_but_nothing_breaks(self):
        html = read("static", "system.html")
        self.assertNotIn('id="admin-material-advanced"', html)
        self.assertNotIn('id="admin-materials-list"', html)
        materials = read("static", "admin-materials.js")
        # Callers still refresh the shared cache when the list panel is absent.
        self.assertIn("await window.fetchAdminMaterials(force);\n      return;", materials)
        # Atlas wizard and index rebuild work from the course overview.
        self.assertIn("document.getElementById('admin-course-workspace')", materials)
        self.assertIn("window.renderAdminCourseMaterialHub?.(true)", materials)
        self.assertIn("已重建索引", materials)


if __name__ == "__main__":
    unittest.main()
