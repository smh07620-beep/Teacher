import unittest
from pathlib import Path


ROOT=Path(__file__).parents[1]


class F2CourseTrackingUiTests(unittest.TestCase):
    def test_tracking_ui_is_course_centric_and_actionable(self):
        source=ROOT.joinpath("static","teacher-course-tracking-f2.js").read_text(encoding="utf-8")
        self.assertIn("course-tracking?courseId=",source)
        for marker in ("未開始","進行中","已完成","已逾期","未通過","學習追蹤"):
            self.assertIn(marker,source)
        self.assertIn("data-course-card-actions",source)

    def test_asset_is_registered(self):
        source=ROOT.joinpath("teacher_app","frontend","assets.py").read_text(encoding="utf-8")
        self.assertIn('"/teacher-course-tracking-f2.js"',source)


if __name__=="__main__":
    unittest.main()
