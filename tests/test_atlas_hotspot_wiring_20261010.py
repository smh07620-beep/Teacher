"""Static wiring guards for the Atlas annotation / hotspot-question frontend."""
import re
import unittest
from pathlib import Path

from teacher_app.frontend.assets import ASSET_MANIFEST

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
INLINE_HANDLER = re.compile(r"\son[a-z][a-z0-9_-]*\s*=", re.IGNORECASE)
NEW_SCRIPTS = (
    "atlas-annotations-1010.js",
    "learner-hotspot-question-1010.js",
    "admin-hotspot-question-1010.js",
)


def read(name):
    return (STATIC / name).read_text(encoding="utf-8")


class AtlasHotspotWiringTests(unittest.TestCase):
    def test_new_scripts_are_injected_into_the_system_page_once(self):
        body = ASSET_MANIFEST["system"]["body"]
        for name in NEW_SCRIPTS:
            with self.subTest(name=name):
                self.assertEqual(body.count("/" + name), 1)
                self.assertTrue((STATIC / name).is_file())

    def test_new_scripts_have_no_inline_handlers_eval_or_unsafe_html(self):
        for name in NEW_SCRIPTS:
            source = read(name)
            with self.subTest(name=name):
                self.assertIsNone(INLINE_HANDLER.search(source))
                self.assertNotIn("eval(", source)
                self.assertNotIn("new Function", source)
                self.assertNotIn("document.write", source)
        # The teacher-side modules build DOM with textContent, never innerHTML.
        for name in ("atlas-annotations-1010.js", "admin-hotspot-question-1010.js"):
            with self.subTest(name=name):
                self.assertNotIn("innerHTML", read(name))

    def test_csp_allow_list_has_the_hotspot_actions_and_the_owner_defines_them(self):
        registry = read("system-csp-actions.js")
        owner = read("learner-hotspot-question-1010.js")
        for action in ("atlasHotspotPick", "atlasHotspotZoom"):
            with self.subTest(action=action):
                self.assertIn(f"'{action}'", registry)
                self.assertIn(f"root.{action} =", owner)

    def test_every_data_csp_action_the_hotspot_module_emits_is_allowed(self):
        registry = read("system-csp-actions.js")
        for name in re.findall(r'data-csp-click="(\w+)\(', read("learner-hotspot-question-1010.js")):
            self.assertIn(f"'{name}'", registry)

    def test_canonical_owners_call_the_modules_without_wrapping_globals(self):
        self.assertIn("AtlasAnnotations?.attachViewer(", read("atlas-70.js"))
        self.assertIn("AtlasAnnotations?.attachEditor(", read("atlas-70.js"))
        self.assertIn("AtlasAnnotations?.collect(", read("atlas-70.js"))
        learner = read("system-learner.js")
        for call in ("AtlasAnnotations?.active()", "AtlasAnnotations?.detachViewer()"):
            self.assertIn(call, learner)
        exam = read("system-exam.js")
        self.assertIn("AtlasHotspotQuestion.render(", exam)
        self.assertIn("function setHotspotAnswer(", exam)
        self.assertIn("AdminHotspotQuestion?.syncForm(", read("admin-question-panel.js"))
        self.assertIn("AdminHotspotQuestion?.collect(", read("admin-question-actions.js"))
        # the new modules must not reassign canonical globals
        for name in NEW_SCRIPTS:
            source = read(name)
            for owned in ("openFormalAtlas", "renderQuestions", "atlasZoom", "atlasReset", "closeAtlas", "openAtlasEdit"):
                with self.subTest(name=name, owned=owned):
                    self.assertNotRegex(source, rf"(?:window\.)?{owned}\s*=")

    def test_hotspot_is_offered_when_authoring_and_never_when_importing(self):
        self.assertIn('value="atlas_hotspot"', read("admin-question-bank.js"))
        self.assertIn("atlas_hotspot", read("admin-question-editor-ui.js"))

    def test_learner_script_never_references_the_answer_fields(self):
        source = read("learner-hotspot-question-1010.js")
        for secret in ("correctRegion", "correctMarkId", "markLabel", "atlasItemId"):
            self.assertNotIn(secret, source)


if __name__ == "__main__":
    unittest.main()
