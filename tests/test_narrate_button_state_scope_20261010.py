"""Regression: clicking 錄旁白 threw "ReferenceError: state is not defined"."""
import re
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "static" / "admin-course-material.js"


class NarrateButtonScopeTest(unittest.TestCase):
    def test_narrate_handler_does_not_use_bare_state(self):
        text = SOURCE.read_text(encoding="utf-8")
        start = text.index("function bindMaterialNarrationControls(")
        end = text.index("function adminHubMaterialRow(")
        body = text[start:end]
        self.assertIsNone(re.search(r"(?<![\w.])state\.", body), "handler must not reference an out-of-scope `state`")
        self.assertIn("box._adminCourseMaterialState", body)


if __name__ == "__main__":
    unittest.main()
