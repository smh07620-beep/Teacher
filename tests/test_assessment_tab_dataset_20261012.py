"""Assessment tabs must read data-assessment-tab-1030 via getAttribute.

``dataset`` camel-cases only dash+letter, so ``data-assessment-tab-1030`` is
``dataset['assessmentTab-1030']`` and ``dataset.assessmentTab1030`` is always
undefined, which made every tab button a silent no-op.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class AssessmentTabAttributeTests(unittest.TestCase):
    def test_no_dataset_access_for_digit_suffixed_tab_attribute(self):
        for name in ("teacher-workspace-1014.js", "teacher-assessment-inline-1031.js"):
            source = (ROOT / "static" / name).read_text(encoding="utf-8")
            self.assertNotIn("dataset.assessmentTab1030", source, name)
            self.assertIn("getAttribute('data-assessment-tab-1030')", source, name)


if __name__ == "__main__":
    unittest.main()
