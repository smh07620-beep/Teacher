from collections import defaultdict
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
OWNERSHIP = ROOT / "docs" / "FRONTEND_JS_OWNERSHIP.md"

WINDOW_ASSIGNMENT = re.compile(r"\bwindow\.([A-Za-z_$][\w$]*)\s*=")
TOP_LEVEL_FUNCTION = re.compile(r"(?m)^(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(")


class FrontendGlobalOwnerGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = OWNERSHIP.read_text(encoding="utf-8")
        cls.sources = {
            path.name: path.read_text(encoding="utf-8")
            for path in sorted(STATIC.glob("*.js"))
        }

    def assert_documented_duplicates(self, pattern, label):
        owners = defaultdict(set)
        for filename, source in self.sources.items():
            for name in pattern.findall(source):
                owners[name].add(filename)
        duplicates = {
            name: sorted(files)
            for name, files in owners.items()
            if len(files) > 1
        }
        undocumented = {
            name: files
            for name, files in duplicates.items()
            if f"`{name}`" not in self.doc
        }
        self.assertFalse(
            undocumented,
            f"Undocumented duplicate {label} owners: {undocumented}",
        )

    def test_duplicate_window_assignments_are_explicitly_documented(self):
        self.assert_documented_duplicates(WINDOW_ASSIGNMENT, "window global")

    def test_duplicate_top_level_function_declarations_are_explicitly_documented(self):
        self.assert_documented_duplicates(TOP_LEVEL_FUNCTION, "top-level function")

    def test_removed_timing_based_owners_do_not_return(self):
        roles = self.sources["roles-signing-66.js"]
        rbac = self.sources["rbac-ui-681.js"]
        teaching = self.sources["teaching.js"]
        self.assertNotIn("window.createAdminUserAccount =", roles)
        self.assertNotIn("window.fetchAdminMaterials =", rbac)
        self.assertNotIn("function markMaterialComplete(", teaching)
        self.assertNotIn("function renderCourseOverview()", teaching)


if __name__ == "__main__":
    unittest.main()
