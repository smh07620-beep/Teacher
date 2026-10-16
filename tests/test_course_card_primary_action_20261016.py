import unittest
from pathlib import Path

JS = (Path(__file__).resolve().parents[1] / "static" / "teaching.js").read_text(encoding="utf-8")


class CourseCardPrimaryActionTests(unittest.TestCase):
    def test_single_state_driven_primary_button(self):
        self.assertIn("function teachingPrimaryAction(", JS)
        for label in ("開始閱讀", "繼續閱讀（", "前往考試", "未通過｜複習第", "已完成"):
            self.assertIn(label, JS)
        self.assertIn("${primaryAction}", JS)

    def test_old_ungated_exam_copy_is_gone(self):
        self.assertNotIn("看完教材即可直接考核，不需先按完成標記", JS)


if __name__ == "__main__":
    unittest.main()
