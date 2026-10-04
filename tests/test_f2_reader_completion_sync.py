import unittest
from pathlib import Path


ROOT=Path(__file__).parents[1]


class F2ReaderCompletionSyncTests(unittest.TestCase):
    def test_canonical_owner_exposes_completion_read_and_sync(self):
        source=ROOT.joinpath("static","system-learner.js").read_text(encoding="utf-8")
        self.assertIn("isComplete(materialId)",source)
        self.assertIn("syncComplete(materialId, completedAt)",source)

    def test_sequential_unlock_reads_canonical_completion_owner(self):
        source=ROOT.joinpath("static","teaching.js").read_text(encoding="utf-8")
        self.assertIn("LearnerMaterialProgress?.isComplete?.(id)",source)

    def test_smart_completion_syncs_and_unlocks_immediately(self):
        source=ROOT.joinpath("static","learner-reading-progress-f2.js").read_text(encoding="utf-8")
        self.assertIn("LearnerMaterialProgress?.syncComplete?.",source)
        self.assertIn("teacher66:material-complete",source)


if __name__=="__main__":
    unittest.main()
