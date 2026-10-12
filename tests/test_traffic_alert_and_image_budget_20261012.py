"""GitHub-run traffic alert exists, and referenced images stay small (Render egress)."""
import re
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
MAX_IMAGE_BYTES = 450 * 1024
MAX_PNG_BYTES = 150 * 1024


class TrafficAlertWorkflowTests(unittest.TestCase):
    def test_workflow_runs_script_and_does_not_need_render_smtp(self):
        text = (ROOT / ".github" / "workflows" / "traffic-alert.yml").read_text(encoding="utf-8")
        self.assertIn("python -u scripts/send_traffic_alert.py", text)
        self.assertIn("TRAFFIC_ALERT_GB", text)
        self.assertIn("secrets.DATABASE_URL", text)

    def test_script_requires_a_recipient(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("send_traffic_alert", ROOT / "scripts" / "send_traffic_alert.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with mock.patch.dict("os.environ", {"TRAFFIC_ALERT_EMAIL": ""}):
            self.assertEqual(module.main(), 1)


class ReferencedImageBudgetTests(unittest.TestCase):
    def test_every_referenced_asset_image_is_small(self):
        pattern = re.compile(r"/assets/[A-Za-z0-9_./-]+\.(?:png|jpg|jpeg|webp)")
        pattern = re.compile(r"/assets/[A-Za-z0-9_./-]+\.(?:png|jpg|jpeg|webp)")
        refs = set()
        for path in [*STATIC.glob("*.css"), *STATIC.glob("*.html"), *STATIC.glob("*.js")]:
            refs.update(pattern.findall(path.read_text(encoding="utf-8", errors="ignore")))
        for ref in sorted(refs):
            file = STATIC / ref.lstrip("/")
            if not file.exists():
                continue
            size = file.stat().st_size
            self.assertLessEqual(size, MAX_IMAGE_BYTES, f"{ref} is {size} bytes")
            if file.suffix == ".png":
                self.assertLessEqual(size, MAX_PNG_BYTES, f"{ref} should be WebP ({size} bytes)")


if __name__ == "__main__":
    unittest.main()
