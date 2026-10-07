"""Environment-variable contract: docs are current and config files have no dead keys."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import env_reference  # noqa: E402

# Keys that code does not read through Python on purpose.
SCRIPT_ONLY = {
    # read by the PowerShell supervisor / updater scripts
    "MATERIAL_WORKER_RELEASE_REF",
    "MATERIAL_WORKER_RELEASE_COMMIT",
    "MATERIAL_WORKER_REQUIRE_SIGNED_TAG",
    # read by gunicorn / run_web.sh
    "GUNICORN_TIMEOUT",
}
# Known dead settings: documented in .local-worker.env.example but read by nothing.
# Remove from the example (or implement them) and then delete from this set.
KNOWN_DEAD = {"AI_PRESENTATION_MAX_ARTIFACT_MB", "AI_PRESENTATION_MAX_TEMPLATE_MB"}


class EnvContractTests(unittest.TestCase):
    def test_reference_is_current(self):
        self.assertEqual(
            (ROOT / "docs" / "ENVIRONMENT_REFERENCE.md").read_text(encoding="utf-8"),
            env_reference.build(),
            "docs/ENVIRONMENT_REFERENCE.md is stale: run python tools/env_reference.py",
        )

    def test_config_files_have_no_misspelled_or_dead_keys(self):
        known = env_reference.code_literals() | set(env_reference.scan()) | SCRIPT_ONLY | KNOWN_DEAD
        self.assertEqual(sorted(env_reference.example_keys() - known), [], ".local-worker.env.example has keys no code reads")
        self.assertEqual(sorted(env_reference.render_keys() - known), [], "render.yaml has keys no code reads")

    def test_worker_secrets_are_documented_in_example(self):
        example = env_reference.example_keys()
        for name in ("TEACHER_BASE_URL", "MATERIAL_WORKER_TOKEN", "WORKER_SITE_VERSION_CHECK_MINUTES"):
            self.assertIn(name, example)


if __name__ == "__main__":
    unittest.main()
