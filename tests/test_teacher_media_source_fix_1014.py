from pathlib import Path
import unittest
from unittest.mock import patch

from teacher_app.frontend.assets import ASSET_MANIFEST
from teacher_app.materials import media_script_jobs


ROOT = Path(__file__).resolve().parents[1]


class TeacherMediaSourceFix1014Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "static" / "teacher-media-source-fix-1014.js").read_text(encoding="utf-8")
        cls.routes = (ROOT / "teacher_app" / "materials" / "media_script_routes.py").read_text(encoding="utf-8")
        cls.jobs = (ROOT / "teacher_app" / "materials" / "media_script_jobs.py").read_text(encoding="utf-8")
        cls.studio = (ROOT / "static" / "teacher-ai-media-studio-1018.js").read_text(encoding="utf-8")
        cls.controls = (ROOT / "static" / "teacher-ai-media-controls-1023.js").read_text(encoding="utf-8")
        cls.script = (ROOT / "static" / "teacher-media-script-1014.js").read_text(encoding="utf-8")

    def test_fix_loads_after_script_studio(self):
        body = ASSET_MANIFEST["system"]["body"]
        self.assertIn("/teacher-media-source-fix-1014.js", body)
        self.assertLess(body.index("/teacher-media-script-1014.js"), body.index("/teacher-media-source-fix-1014.js"))

    def test_picker_uses_uploaded_materials_and_explains_builtin_limitation(self):
        for marker in (
            "/api/slides/admin",
            "!item.isBuiltin",
            "草稿也可先做講稿",
            "內建舊教材因沒有原始文字來源不列入",
            "↻ 重新整理教材",
        ):
            self.assertIn(marker, self.source)

    def test_scoped_teacher_picker_stays_in_preferred_group(self):
        self.assertIn("R.scopedTeacher", self.source)
        self.assertIn("preferredGroup", self.source)
        self.assertIn("String(item.group || '') === preferredGroup", self.source)

    def test_source_picker_has_one_canonical_runtime_owner(self):
        self.assertIn("TeacherAIMediaControls1023", self.source)
        self.assertNotIn("setTimeout(() => void refreshMaterials()", self.source)
        self.assertNotIn("TeacherMediaSourceFix1014?.refreshMaterials?.()", self.studio)
        self.assertIn("teacher-media-source-options-1014", self.controls)
        self.assertIn("teacher-media-source-options-1014", self.script)
        self.assertNotIn("item.active !== false", self.script)

    def test_draft_material_is_valid_media_authoring_source(self):
        draft = {"id": "mat-draft", "group": "grpBio", "area": "internal", "active": False}
        actor = {"username": "teacher1"}
        with patch.object(media_script_jobs.material_repository, "get_material", return_value=draft):
            request = media_script_jobs.prepare_request({"materialId": "mat-draft"}, actor)
        self.assertEqual(request["material_id"], "mat-draft")
        self.assertEqual(request["group_key"], "grpBio")

    def test_worker_can_generate_from_draft_but_not_missing_material(self):
        draft = {"id": "mat-draft", "group": "grpBio", "area": "internal", "active": False}
        with patch.object(media_script_jobs.material_repository, "get_material", return_value=draft), \
             patch.object(media_script_jobs.media_script_runtime, "generate_script", return_value={"title": "ok"}) as generate:
            result = media_script_jobs.run_generation_sync({"materialId": "mat-draft"})
        self.assertEqual(result["title"], "ok")
        generate.assert_called_once()
        with patch.object(media_script_jobs.material_repository, "get_material", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "教材已不存在"):
                media_script_jobs.run_generation_sync({"materialId": "missing"})

    def test_publication_is_not_bypassed_by_media_authoring(self):
        self.assertIn("Publication remains a separate explicit step", self.routes)
        self.assertNotIn("material.publish", self.jobs)
        self.assertNotIn("/api/media-scripts/publish", self.source)


if __name__ == "__main__":
    unittest.main()
