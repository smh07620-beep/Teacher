from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LearnerStudyExamLoop1032Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loop = (ROOT / "static" / "learner-study-exam-loop-1032.js").read_text(encoding="utf-8")
        cls.teaching = (ROOT / "static" / "teaching.js").read_text(encoding="utf-8")
        cls.results = (ROOT / "static" / "admin-results-data.js").read_text(encoding="utf-8")
        cls.assets = (ROOT / "teacher_app" / "frontend" / "assets.py").read_text(encoding="utf-8")

    def test_loop_script_is_loaded(self):
        self.assertIn('"/learner-study-exam-loop-1032.js"', self.assets)

    def test_material_completion_is_not_a_gate(self):
        self.assertNotIn("請先完成目前這份教材，再進入下一份教材。", self.teaching)
        self.assertIn("看完了，直接考核", self.loop)

    def test_learner_can_return_to_study_and_keep_result(self):
        for marker in ("回教材閱覽", "回圖譜區", "回到考核", "loop1032:lastResult:", "未通過"):
            self.assertIn(marker, self.loop)

    def test_teacher_results_group_by_role_and_keep_passing_attempt(self):
        self.assertIn("人員別", self.results)
        self.assertIn("顯示通過成績", self.results)


if __name__ == "__main__":
    unittest.main()
