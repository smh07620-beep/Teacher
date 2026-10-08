import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class UnassignedMoreMenuTests(unittest.TestCase):
    def test_unassigned_group_does_not_clip_the_more_menu(self):
        js = (ROOT / "static" / "admin-course-material.js").read_text(encoding="utf-8")
        tag = re.search(r'<details data-unassigned-group class="([^"]*)"', js)
        self.assertIsNotNone(tag)
        self.assertNotIn("overflow-hidden", tag.group(1))
        css = (ROOT / "static" / "admin.css").read_text(encoding="utf-8")
        self.assertIn("details[data-unassigned-group] [data-material-more][open]", css)


if __name__ == "__main__":
    unittest.main()
