import unittest
from pathlib import Path

ROOT=Path(__file__).parents[1]

class FeatureExposure681Tests(unittest.TestCase):
    def test_matrix_classifies_68_features_and_no_orphan_modules_remain(self):
        matrix=ROOT.joinpath("FEATURE_EXPOSURE_681.md").read_text(encoding="utf-8")
        for feature in ("External YouTube/Shorts", "Question Bank 2.0 drafts", "Blueprint snapshots", "Item analytics", "Admin elevation"):
            self.assertIn(feature,matrix)
        self.assertFalse(ROOT.joinpath("static/media-player-68.js").exists())
        self.assertFalse(ROOT.joinpath("static/admin-elevation-68.js").exists())

