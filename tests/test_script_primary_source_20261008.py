"""Narration Step 1: a chosen/pasted source is the primary material; the old dropdown must not gate generation."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(name):
    return ROOT.joinpath("static", name).read_text(encoding="utf-8")


class ScriptPrimarySourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = _read("teacher-media-script-1014.js")
        cls.audio = _read("teacher-media-audio-1014.js")

    def test_new_upload_becomes_primary_without_the_dropdown(self):
        # The primary source is remembered in a variable; other scripts repaint the dropdown and clear it.
        self.assertIn("let primarySourceId = ''", self.script)
        self.assertIn("function currentMaterialId()", self.script)
        self.assertIn("primarySourceId || document.getElementById('teacher-script-material-1014')?.value", self.script)
        self.assertIn("const materialId = currentMaterialId();", self.script)
        self.assertNotIn("請先選擇一份教材", self.script)

    def test_upload_does_not_dispatch_change_that_resets_the_selection(self):
        start = self.script.index("async function uploadScriptSources")
        end = self.script.index("async function addPastedScriptSource")
        self.assertNotIn("dispatchEvent", self.script[start:end])
        self.assertIn("function applyPrimarySelection", self.script)

    def test_existing_material_picker_is_collapsed_and_not_the_default_path(self):
        self.assertIn('id="teacher-script-existing-source-1033"', self.script)
        self.assertIn("改用已有教材", self.script)
        # Only an opened picker counts as the teacher's explicit choice.
        self.assertIn("details.open", self.script)
        self.assertIn("選好檔案後，請直接按下方", self.script)

    def test_user_picking_another_material_drops_the_remembered_upload(self):
        self.assertIn("event.isTrusted", self.script)
        self.assertIn("primarySourceId = ''", self.script)

    def test_generate_button_stays_disabled_until_a_source_is_ready(self):
        self.assertIn("function sourcesReady()", self.script)
        self.assertIn("function updateGenerateState()", self.script)
        self.assertIn("generate.disabled = busyNow || !ready", self.script)
        # Too-short pasted text does not count as a ready source.
        self.assertIn("if (pasted && pasted.length < 20) return false;", self.script)
        # Re-evaluated whenever the teacher changes a file, the pasted text or the picked material.
        self.assertIn("'teacher-script-source-file-1030')?.addEventListener('change', onSourceInputsChanged)", self.script)
        self.assertIn("'teacher-script-paste-1030')?.addEventListener('input', onSourceInputsChanged)", self.script)
        # The old unconditional enable in setBusy is gone.
        self.assertNotIn("if (generate) generate.disabled = busy;", self.script)

    def test_audio_step_reads_the_same_source(self):
        self.assertIn("currentMaterialId", self.script[self.script.index("window.TeacherMediaScript1014"):])
        self.assertIn("TeacherMediaScript1014?.currentMaterialId?.()", self.audio)

    def test_audio_panel_shows_the_real_backend_reason(self):
        self.assertIn("data?.diagnostic?.message", self.audio)
        self.assertIn("原因：", self.audio)


if __name__ == "__main__":
    unittest.main()
