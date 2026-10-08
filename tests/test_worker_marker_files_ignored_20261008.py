"""Files the Worker supervisors create inside the checkout must be git-ignored.

update_material_worker.ps1 refuses to update a dirty working tree (including untracked
files), so any unignored marker file silently blocks every automatic Worker update.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUPERVISORS = (
    "run_ai_worker_autostart.ps1",
    "run_material_worker_autostart.ps1",
    "install_material_worker_task.ps1",
)


class WorkerMarkerFilesIgnoredTests(unittest.TestCase):
    def test_every_dot_file_a_supervisor_writes_into_the_checkout_is_ignored(self):
        ignored = {line.strip() for line in ROOT.joinpath(".gitignore").read_text(encoding="utf-8").splitlines()}
        marker_names = set()
        for name in SUPERVISORS:
            text = ROOT.joinpath(name).read_text(encoding="utf-8")
            marker_names.update(re.findall(r'Join-Path\s+\$root\s+"(\.[A-Za-z0-9._-]+)"', text))
        self.assertIn(".ai-worker-requirements.sha256", marker_names)
        missing = sorted(name for name in marker_names if name not in ignored)
        self.assertEqual(missing, [], f"add to .gitignore or the Worker updater will refuse a dirty tree: {missing}")


if __name__ == "__main__":
    unittest.main()
