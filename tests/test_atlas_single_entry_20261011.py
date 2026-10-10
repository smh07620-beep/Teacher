"""Word -> Atlas has one teacher entry point (course wizard), then framing."""
import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "static"


def read(name):
    return (STATIC / name).read_text(encoding="utf-8")


class AtlasSingleEntryTests(unittest.TestCase):
    def test_only_the_course_wizard_opens_the_word_import(self):
        self.assertIn("courseWizard681OpenAtlasImport", read("course-wizard-681.js"))
        for name in ("admin-materials.js", "admin-course-material.js", "teacher-content-studio-71.js", "system-csp-actions.js"):
            with self.subTest(name=name):
                src = read(name)
                self.assertNotIn("openAdminMaterialAtlasImport", src)
                self.assertNotIn("openTeacherAtlasDocxWorkspace", src)
                self.assertNotIn("openAtlasCreate", src.replace("'openAtlasCreate',", "")) if name == "system-csp-actions.js" else None
        for name in ("admin-materials.js", "admin-course-material.js", "teacher-content-studio-71.js"):
            self.assertNotIn("openAtlasDocxWizard", read(name))

    def test_single_image_upload_is_admin_only_in_the_browser_too(self):
        src = read("atlas-70.js")
        self.assertIn("window.atlasDirectUpload", src)
        self.assertIn("課程精靈", src)

    def test_import_goes_straight_to_framing(self):
        src = read("atlas-docx-wizard-70.js")
        self.assertIn("framingStep(", src)
        self.assertIn("AtlasAnnotations.attachEditor(form,item)", src)
        self.assertIn("annotationJson", src)


if __name__ == "__main__":
    unittest.main()
