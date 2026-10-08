"""A different commit (same VERSION) only warns; a different VERSION still blocks."""
import os
import unittest
from unittest.mock import patch

from teacher_app.materials import media_audio_routes
from tests.test_ai_worker_fleet_status_20261008 import _beat


def _status(version, web_version="6.8.1"):
    row = _beat("pc1-ai", 10, sha="aaaaaaa1111")
    row["capabilities"]["workerVersion"] = version
    with patch.dict(os.environ, {"RENDER_GIT_COMMIT": "bbbbbbb2222"}), \
         patch.object(media_audio_routes, "_web_version", return_value=web_version), \
         patch.object(media_audio_routes.worker_repository, "list_heartbeats", return_value=[row]):
        return media_audio_routes._ai_worker_status()


class SmallDriftTests(unittest.TestCase):
    def test_other_commit_same_version_stays_usable(self):
        status = _status("6.8.1")
        self.assertTrue(media_audio_routes._worker_is_ready(status))
        self.assertEqual(status["diagnosticCode"], "worker_code_behind")
        self.assertIs(status["codeIdentityMatch"], False)

    def test_different_version_is_still_blocked(self):
        status = _status("6.7.0")
        self.assertFalse(media_audio_routes._worker_is_ready(status))
        self.assertEqual(status["diagnosticCode"], "worker_code_mismatch")


if __name__ == "__main__":
    unittest.main()
