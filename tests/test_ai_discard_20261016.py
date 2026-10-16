"""Immediate discard of unpublished AI decks/videos (shares the 24h purge safety rules)."""
import datetime as dt
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


FRESH = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)).isoformat()


retention = None


class FakeRuntime:
    def delete_adapters(self, **_kw):
        return {}


class DiscardTests(unittest.TestCase):
    def setUp(self):
        # Imported here: importing migration modules at collection time changes the
        # global migration registry order and breaks the release-contract tests.
        from teacher_app.maintenance import retention as _retention
        from teacher_app.maintenance.ai_presentation_migration import (
            ai_presentation_production_hardening_100, ai_presentations_99)
        from teacher_app.maintenance.ai_video_migration import ai_presentation_videos_101
        from teacher_app.materials import schema as material_schema

        global retention
        retention = _retention
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "t.db")
        self.env = patch.dict(os.environ, {"TEACHER_SQLITE_PATH": self.db, "DATABASE_URL": ""})
        self.env.start()
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        for fn in (ai_presentations_99, ai_presentation_production_hardening_100, ai_presentation_videos_101,
                   material_schema.init_schema):
            fn(conn, "sqlite")
        conn.commit()
        self.conn = conn
        self.deleted = []
        self.patches = [
            patch.object(retention, "_delete_artifact", side_effect=lambda backend, key, **kw: self.deleted.append(key)),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.env.stop()
        self.conn.close()
        self.tmp.cleanup()

    def _pres(self, pid, status, updated):
        self.conn.execute(
            "INSERT INTO ai_presentations(id,material_id,draft_id,group_key,training_area,title,status,artifact_backend,"
            "artifact_storage_key,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (pid, "m", "d", "g", "a", pid, status, "r2", f"k/{pid}", updated, updated))
        self.conn.commit()

    def _video(self, vid, status, updated, pres="p-x"):
        self.conn.execute(
            "INSERT INTO ai_presentation_videos(id,presentation_id,group_key,training_area,title,status,artifact_backend,"
            "artifact_storage_key,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (vid, pres, "g", "a", vid, status, "r2", f"k/{vid}", updated, updated))
        self.conn.commit()

    def _count(self, table):
        return self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def test_discard_fresh_draft_deletes_row_and_artifact(self):
        self._pres("p1", "draft", FRESH)
        retention.discard_presentation("p1", storage_runtime=FakeRuntime())
        self.assertEqual(self._count("ai_presentations"), 0)
        self.assertIn("k/p1", self.deleted)

    def test_published_deck_cannot_be_discarded(self):
        self._pres("p1", "published", FRESH)
        with self.assertRaises(retention.DiscardBlocked) as caught:
            retention.discard_presentation("p1", storage_runtime=FakeRuntime())
        self.assertEqual(caught.exception.code, "published")
        self.assertEqual(self._count("ai_presentations"), 1)

    def test_deck_used_by_a_video_is_blocked_until_video_is_discarded(self):
        self._pres("p1", "approved", FRESH)
        self._video("v1", "draft", FRESH, pres="p1")
        with self.assertRaises(retention.DiscardBlocked) as caught:
            retention.discard_presentation("p1", storage_runtime=FakeRuntime())
        self.assertEqual(caught.exception.code, "in_use")
        retention.discard_video("v1", storage_runtime=FakeRuntime())
        retention.discard_presentation("p1", storage_runtime=FakeRuntime())
        self.assertEqual((self._count("ai_presentations"), self._count("ai_presentation_videos")), (0, 0))

    def test_published_video_cannot_be_discarded_and_missing_is_not_found(self):
        self._video("v1", "published", FRESH)
        with self.assertRaises(retention.DiscardBlocked):
            retention.discard_video("v1", storage_runtime=FakeRuntime())
        with self.assertRaises(retention.DiscardBlocked) as caught:
            retention.discard_video("nope", storage_runtime=FakeRuntime())
        self.assertEqual(caught.exception.code, "not_found")


if __name__ == "__main__":
    unittest.main()
