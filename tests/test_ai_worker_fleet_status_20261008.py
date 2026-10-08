"""Several AI Workers: one healthy worker is enough, a broken newer one must not hide it."""
import datetime as dt
import unittest
from unittest.mock import patch

from teacher_app.materials import media_audio_routes


def _beat(worker_id, seconds_ago, *, kokoro=True, sha="abc1234"):
    seen = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=seconds_ago)
    return {
        "worker_id": worker_id,
        "last_seen": seen.isoformat(),
        "capabilities": {
            "workerKind": "ai",
            "workerSha": sha,
            "heartbeatContract": 4,
            "heartbeatTransport": "https",
            "controlPlaneReady": True,
            "queues": ["ai_questions", "media_audio"],
            "kokoro": {"available": kokoro},
        },
    }


def _status(rows):
    with patch.object(media_audio_routes.worker_repository, "list_heartbeats", return_value=rows):
        return media_audio_routes._ai_worker_status()


class AIWorkerFleetStatusTests(unittest.TestCase):
    def test_single_healthy_worker_is_ready(self):
        status = _status([_beat("pc1-ai", 10)])
        self.assertTrue(media_audio_routes._worker_is_ready(status))
        self.assertEqual(status["workerId"], "pc1-ai")

    def test_healthy_worker_wins_over_a_newer_broken_one(self):
        status = _status([_beat("pc2-ai", 5, kokoro=False), _beat("pc1-ai", 40)])
        self.assertTrue(media_audio_routes._worker_is_ready(status))
        self.assertEqual(status["workerId"], "pc1-ai")
        self.assertEqual(status["onlineWorkers"], 2)
        self.assertEqual(status["readyWorkers"], 1)

    def test_an_offline_healthy_worker_does_not_count(self):
        status = _status([_beat("pc2-ai", 5, kokoro=False), _beat("pc1-ai", 900)])
        self.assertFalse(media_audio_routes._worker_is_ready(status))
        self.assertEqual(status["workerId"], "pc2-ai")
        self.assertEqual(status["diagnosticCode"], "kokoro_unavailable")

    def test_outdated_worker_without_version_is_not_ready_but_others_are(self):
        status = _status([_beat("old-ai", 5, sha=""), _beat("pc1-ai", 30)])
        self.assertTrue(media_audio_routes._worker_is_ready(status))
        self.assertEqual(status["workerId"], "pc1-ai")

    def test_no_ai_worker_keeps_the_not_seen_diagnostic(self):
        status = _status([])
        self.assertFalse(status["online"])
        self.assertEqual(status["diagnosticCode"], "worker_not_seen")


if __name__ == "__main__":
    unittest.main()
