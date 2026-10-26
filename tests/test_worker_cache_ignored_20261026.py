"""Worker runtime caches inside the checkout must be git-ignored (2026-10-26).

The safe updater refuses to run on a dirty working tree, so an un-ignored
cache folder silently blocks every Worker update.
"""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class WorkerCacheIgnoredTests(unittest.TestCase):
    def test_video_cache_is_ignored(self):
        result = subprocess.run(["git", "check-ignore", "-q", ".video_cache/clip.mp4"], cwd=ROOT)
        self.assertEqual(result.returncode, 0, ".video_cache/ must be listed in .gitignore")


if __name__ == "__main__":
    unittest.main()
