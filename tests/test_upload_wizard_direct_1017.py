"""Course-wizard uploads go Browser -> R2 only; the rule lives in the upload owner (2026-10-17)."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class WizardDirectUploadTests(unittest.TestCase):
    def test_owner_forces_direct_upload_for_wizard_forms(self):
        src = (ROOT / "static" / "material-upload-client.js").read_text(encoding="utf-8")
        self.assertIn("formData.get('bundleWorkflowId')", src)
        self.assertIn("fallbackToSameOriginQueue:false", src)
        self.assertIn("delete directOptions.onFallback", src)
        controls = (ROOT / "static" / "teacher-ai-media-controls-1023.js").read_text(encoding="utf-8")
        self.assertNotIn("client.enqueue = wrapped", controls)

    @unittest.skipUnless(shutil.which("node"), "node required")
    def test_wizard_options_reach_direct_upload_without_fallback(self):
        script = r"""
const fs = require('fs'), vm = require('vm');
const code = fs.readFileSync('static/material-upload-client.js', 'utf8')
  .replace('async function directUpload(', 'async function directUploadReal(')
  + '\nasync function directUpload(form, options){ globalThis.seen = options; return {accepted:true}; }';
const window = {}; const ctx = { window, console, globalThis: {}, fetch: async () => ({ ok: true, json: async () => ({}) }), crypto: {}, TextEncoder, setTimeout, clearTimeout };
ctx.globalThis = ctx;
vm.createContext(ctx); vm.runInContext(code, ctx);
const form = { get: k => (k === 'bundleWorkflowId' ? 'cw-1' : '') };
window.MaterialUploadClient.enqueue(form, { fallbackToSameOriginQueue: true, onFallback() {} }).then(() => {
  console.log(JSON.stringify({ fallback: ctx.seen.fallbackToSameOriginQueue, hasOnFallback: 'onFallback' in ctx.seen }));
});
"""
        out = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn('"fallback":false', out.stdout)
        self.assertIn('"hasOnFallback":false', out.stdout)


if __name__ == "__main__":
    unittest.main()
