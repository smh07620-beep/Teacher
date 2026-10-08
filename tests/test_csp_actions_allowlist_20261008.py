import glob
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSP = (ROOT / "static" / "system-csp-actions.js").read_text(encoding="utf-8")
START = CSP.index("ALLOWED_ACTIONS")
ALLOWED = set(re.findall(r"'([A-Za-z_$][\w$]*)'", CSP[START:CSP.index("]);", START)]))
CALL = re.compile(r'data-csp-(?:click|change|input|keydown|submit|pointermove)="(?:[^"]*?;)?\s*(?:window\.)?([A-Za-z_$][\w$]*)\(')
IGNORED = {"if"}


class CspActionAllowlistTests(unittest.TestCase):
    def test_every_data_csp_action_is_allowlisted(self):
        # A name missing from ALLOWED_ACTIONS is blocked at runtime and the button
        # silently does nothing, even though window.<name> exists.
        missing = {}
        for path in glob.glob(str(ROOT / "static" / "*.js")) + glob.glob(str(ROOT / "static" / "*.html")):
            text = Path(path).read_text(encoding="utf-8", errors="ignore")
            for name in CALL.findall(text):
                if name not in ALLOWED and name not in IGNORED:
                    missing.setdefault(name, set()).add(Path(path).name)
        self.assertEqual({}, {k: sorted(v) for k, v in missing.items()})


class WizardGapWarningTests(unittest.TestCase):
    WIZARD = (ROOT / "static" / "course-wizard-681.js").read_text(encoding="utf-8")

    def test_next_warns_before_leaving_an_empty_shell(self):
        self.assertIn("function stepGaps(forStep)", self.WIZARD)
        self.assertIn("仍要前往下一步嗎？", self.WIZARD)
        self.assertIn("這門課目前還沒有任何教材", self.WIZARD)
        self.assertIn("目前沒有建立考卷", self.WIZARD)

    def test_final_step_lists_missing_items(self):
        self.assertIn("發布前請確認", self.WIZARD)


if __name__ == "__main__":
    unittest.main()
