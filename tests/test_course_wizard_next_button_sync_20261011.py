import re
import unittest
from pathlib import Path

SRC = (Path(__file__).resolve().parents[1] / "static" / "course-wizard-681.js").read_text(encoding="utf-8")


def body(name):
    match = re.search(r"function %s\([a-z]*\)\{(.*?)\n\}" % name, SRC.replace("\r\n", "\n"), re.S)
    assert match, name
    return match.group(1)


class NextButtonSyncTests(unittest.TestCase):
    def test_next_button_is_addressable(self):
        self.assertIn('id="cw681-next"', SRC)

    def test_button_state_is_refreshed_without_a_full_render(self):
        # Upload finishing (syncCompletionControls) and busy ending (setBusy) must
        # re-evaluate the button, otherwise it stays disabled until some other click re-renders.
        self.assertIn("syncNextButton();", body("syncCompletionControls"))
        self.assertIn("syncNextButton();", body("setBusy").replace("\r", ""))

    def test_sync_uses_same_rule_as_render(self):
        self.assertIn("state.busy||state.aiBusy||(state.created&&!canLeaveCourse())", body("syncNextButton"))



class DisabledMaterialsVisibleTests(unittest.TestCase):
    def test_course_material_list_uses_admin_endpoint_so_disabled_ones_show(self):
        text = SRC.replace("\r\n", "\n")
        start = text.index("async function loadMaterials()")
        block = text[start:start + 1500]
        self.assertIn("/api/slides/admin", block)
        # learner-facing list for the "link existing materials" picker stays active-only
        self.assertIn("state.materials=inGroup.filter(m=>m.active!==false)", block)


if __name__ == "__main__":
    unittest.main()
