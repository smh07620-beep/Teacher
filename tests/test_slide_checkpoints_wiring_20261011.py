"""Static guards for the optional slide-checkpoint frontend and contract."""
import re
import unittest
from pathlib import Path

import release_contract
from teacher_app.frontend.assets import ASSET_MANIFEST

STATIC = Path(__file__).resolve().parents[1] / "static"
SCRIPTS = ("learner-slide-checkpoints-1011.js", "admin-slide-checkpoints-1011.js")


def read(name):
    return (STATIC / name).read_text(encoding="utf-8")


class SlideCheckpointWiringTests(unittest.TestCase):
    def test_scripts_injected_once_and_exist(self):
        body = ASSET_MANIFEST["system"]["body"]
        for name in SCRIPTS:
            self.assertEqual(body.count("/" + name), 1)
            self.assertTrue((STATIC / name).is_file())

    def test_no_inline_handlers_eval_or_innerhtml(self):
        for name in SCRIPTS:
            src = read(name)
            self.assertIsNone(re.search(r"\son[a-z][a-z0-9_-]*\s*=", src, re.IGNORECASE))
            self.assertNotIn("innerHTML", src)
            self.assertNotIn("eval(", src)

    def test_viewer_is_observed_not_wrapped(self):
        src = read("learner-slide-checkpoints-1011.js")
        for owned in ("openMaterial", "goToSlidePage", "closeSlideViewer", "openSlideViewer"):
            self.assertNotRegex(src, rf"(?:window\.|root\.)?{owned}\s*=")
        self.assertIn("slideViewerState", src)

    def test_card_never_blocks_reading(self):
        src = read("learner-slide-checkpoints-1011.js")
        self.assertIn("稍後再說", src)
        self.assertIn("答不答都可以繼續閱讀", src)

    def test_menu_entry_only_for_slide_materials_and_action_allowed(self):
        menu = read("admin-course-material.js")
        self.assertIn("openSlideCheckpointEditor('${m.id}')", menu)
        self.assertIn("'openSlideCheckpointEditor'", read("system-csp-actions.js"))
        self.assertIn("root.openSlideCheckpointEditor =", read("admin-slide-checkpoints-1011.js"))

    def test_migration_is_registered_last_and_in_contract(self):
        self.assertEqual(release_contract.REQUIRED_MIGRATIONS[-1], "0118-slide-checkpoints")


if __name__ == "__main__":
    unittest.main()
