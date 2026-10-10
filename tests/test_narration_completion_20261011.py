"""有旁白的投影片教材：翻完頁還要旁白聽到 90% 才算完成（伺服器端判定）(2026-10-11)。"""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from teacher_app.common import db as common_db
from teacher_app.learning import routes as learning_routes
from teacher_app.materials import repository as material_repository

ROOT = Path(__file__).resolve().parents[1]

SLIDES = {"id": "slide-1", "viewerMode": "slides", "currentVersion": 1, "active": True, "group": "grpBio", "area": "internal"}
AUDIO = {
    "id": "audio-1", "viewerMode": "audio", "currentVersion": 1, "active": True, "dateAdded": "2026-10-10",
    "storageMeta": {"mediaKind": "teacher_narration", "sourceMaterialId": "slide-1", "sourceVersion": 1},
}
DDL = (
    "CREATE TABLE learning_progress (material_id TEXT NOT NULL, username TEXT NOT NULL, position TEXT NOT NULL DEFAULT '{}',"
    "progress REAL NOT NULL DEFAULT 0, completed INTEGER NOT NULL DEFAULT 0, last_viewed_at TEXT NOT NULL DEFAULT '',"
    "completed_at TEXT NOT NULL DEFAULT '', last_position_seconds REAL NOT NULL DEFAULT 0, duration REAL NOT NULL DEFAULT 0,"
    "watched_buckets TEXT NOT NULL DEFAULT '[]', completion_threshold REAL NOT NULL DEFAULT 0.9, updated_at TEXT NOT NULL DEFAULT '',"
    "completed_version INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(material_id,username))"
)


class NarrationCompletionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name) / "t.db"
        conn = sqlite3.connect(self.db)
        conn.execute(DDL)
        conn.commit()
        conn.close()
        self.materials = {"slide-1": dict(SLIDES), "audio-1": dict(AUDIO)}
        for target, kwargs in (
            (common_db, {"sqlite_path": self.db}),
        ):
            for name, value in kwargs.items():
                patcher = patch.object(target, name, return_value=value)
                patcher.start()
                self.addCleanup(patcher.stop)
        for patcher in (
            patch.object(material_repository, "list_uploaded_materials", lambda include_inactive=False: list(self.materials.values())),
            patch.object(learning_routes.learning_access, "can_access_learning_item", lambda user, item: True),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY="t", STORAGE_PATHS=SimpleNamespace(uploaded_slides_dir=Path(tmp.name)))
        owner = SimpleNamespace(app=app, _current_user=lambda: {"username": "s1", "role": "student"})
        learning_routes.register_smart_learning(owner, material_getter=lambda mid: self.materials.get(mid))
        self.client = app.test_client()

    def _read_all_pages(self, total=5):
        last = None
        for page in range(1, total + 1):
            last = self.client.put("/api/learning-progress/slide-1", json={"position": {"page": page, "totalPages": total}})
        return last.get_json()

    def _listen(self, seconds, duration=100):
        buckets = list(range(0, seconds // 10))
        return self.client.put(
            "/api/learning-progress/audio-1",
            json={"duration": duration, "lastPositionSeconds": seconds, "watchedBuckets": buckets},
        ).get_json()

    def test_all_pages_without_listening_is_not_complete(self):
        data = self._read_all_pages()
        self.assertFalse(data["completed"])
        self.assertTrue(data["narrationPending"])

    def test_listening_to_ninety_percent_completes_the_slide_material(self):
        self._read_all_pages()
        result = self._listen(90)
        self.assertEqual(result["sourceCompleted"], "slide-1")
        self.assertTrue(self.client.get("/api/learning-progress/slide-1").get_json()["completed"])

    def test_listening_first_then_reading_completes(self):
        self._listen(90)
        data = self._read_all_pages()
        self.assertTrue(data["completed"])

    def test_listening_below_threshold_is_not_enough(self):
        self._read_all_pages()
        result = self._listen(80)
        self.assertEqual(result["sourceCompleted"], "")
        self.assertFalse(self.client.get("/api/learning-progress/slide-1").get_json()["completed"])

    def test_listening_alone_does_not_complete_unread_pages(self):
        self._listen(100)
        self.client.put("/api/learning-progress/slide-1", json={"position": {"page": 5, "totalPages": 5}})
        self.assertFalse(self.client.get("/api/learning-progress/slide-1").get_json()["completed"])

    def test_stale_narration_after_new_version_is_not_required(self):
        self.materials["slide-1"]["currentVersion"] = 2
        data = self._read_all_pages()
        self.assertTrue(data["completed"])
        self.assertFalse(data["narrationPending"])

    def test_material_without_narration_keeps_the_old_rule(self):
        del self.materials["audio-1"]
        self.assertTrue(self._read_all_pages()["completed"])


class NarrationClientTests(unittest.TestCase):
    def test_client_follows_page_turns_and_records_listening(self):
        source = (ROOT / "static" / "learner-narration-1100.js").read_text(encoding="utf-8")
        self.assertIn("seekToPage(shown)", source)
        self.assertNotIn("following=false; refreshFollowButton(); return;", source)
        self.assertIn("watchedBuckets", source)
        self.assertIn("旁白已聽", source)


if __name__ == "__main__":
    unittest.main()
