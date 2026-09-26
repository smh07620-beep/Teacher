import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SavedLearningUi88Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = ROOT.joinpath("static", "system.html").read_text(encoding="utf-8")
        cls.learner = ROOT.joinpath("static", "system-learner.js").read_text(encoding="utf-8")
        cls.teaching = ROOT.joinpath("static", "teaching.js").read_text(encoding="utf-8")
        cls.factory = ROOT.joinpath("teacher_app", "factory.py").read_text(encoding="utf-8")

    def test_saved_shelf_and_cache_buster_are_present(self):
        for token in ('id="saved-learning-items"', 'aria-label="我的收藏"', 'id="saved-learning-items-list"', 'system-learner.js?v=9000'):
            self.assertIn(token, self.html)

    def test_runtime_loads_toggles_and_renders_account_saved_items(self):
        for token in ("/api/saved-learning-items", "toggleSavedLearningItem", "renderSavedLearningShelf", 'data-save-learning-item="material"', "☆ 稍後閱讀", "★ 已收藏", "☆ 收藏課程"):
            self.assertIn(token, self.learner)
        self.assertIn("register_saved_learning_routes", self.factory)

    def test_device_page_bookmark_remains_separate_from_account_saved_items(self):
        self.assertIn("Page bookmarks are device-local, never completion evidence", self.teaching)
        self.assertIn("localStorage.setItem(teachingBookmarkKey", self.teaching)
        saved_runtime = self.learner[self.learner.index("function savedLearningKey"):self.learner.index("function courseMaterialMeta")]
        self.assertNotIn("material-progress", saved_runtime)


if __name__ == "__main__":
    unittest.main()
