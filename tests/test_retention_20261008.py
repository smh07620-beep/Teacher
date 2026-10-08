"""24-hour retention: published AI products stay, expired unpublished ones go."""
import datetime as dt
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from teacher_app.maintenance import retention
from teacher_app.maintenance.ai_presentation_migration import ai_presentation_production_hardening_100, ai_presentations_99
from teacher_app.maintenance.ai_video_migration import ai_presentation_videos_101
from teacher_app.maintenance.ai_material_migration import ai_material_drafts_97
from teacher_app.maintenance.media_script_migration import media_script_jobs_94
from teacher_app.materials import schema as material_schema

NOW = dt.datetime(2026, 10, 10, 12, 0, tzinfo=dt.timezone.utc)
OLD = (NOW - dt.timedelta(hours=30)).isoformat()
FRESH = (NOW - dt.timedelta(hours=2)).isoformat()


class FakeRuntime:
    def delete_adapters(self, **_kw):
        return {}


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "t.db")
        self.env = patch.dict(os.environ, {"TEACHER_SQLITE_PATH": self.db, "DATABASE_URL": ""})
        self.env.start()
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        for fn in (ai_presentations_99, ai_presentation_production_hardening_100, ai_presentation_videos_101,
                   media_script_jobs_94, ai_material_drafts_97, material_schema.init_schema):
            fn(conn, "sqlite")
        conn.commit()
        self.conn = conn
        self.deleted = []
        self.patches = [
            patch.object(retention, "_delete_artifact", side_effect=lambda backend, key, **kw: self.deleted.append(key)),
            patch("teacher_app.common.audit.record_event"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.env.stop()
        self.conn.close()
        self.tmp.cleanup()

    def _pres(self, pid, status, updated, key=None, draft="d"):
        self.conn.execute(
            "INSERT INTO ai_presentations(id,material_id,draft_id,group_key,training_area,title,status,artifact_backend,"
            "artifact_storage_key,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (pid, "m", draft, "g", "a", pid, status, "r2", key or f"k/{pid}", updated, updated))
        self.conn.commit()

    def _video(self, vid, status, updated, pres="p-x"):
        self.conn.execute(
            "INSERT INTO ai_presentation_videos(id,presentation_id,group_key,training_area,title,status,artifact_backend,"
            "artifact_storage_key,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (vid, pres, "g", "a", vid, status, "r2", f"k/{vid}", updated, updated))
        self.conn.commit()

    def _count(self, table):
        return self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def test_unpublished_expired_products_are_removed_published_and_fresh_are_kept(self):
        self._pres("p-old-draft", "draft", OLD)
        self._pres("p-old-approved", "approved", OLD)
        self._pres("p-fresh", "draft", FRESH)
        self._pres("p-published", "published", OLD)
        self._video("v-old", "draft", OLD, pres="p-other")
        self._video("v-published", "published", OLD, pres="p-other")
        summary = retention.purge_expired(now=NOW, hours=24, paths=object(), storage_runtime=FakeRuntime())
        remaining = {r[0] for r in self.conn.execute("SELECT id FROM ai_presentations")}
        self.assertEqual(remaining, {"p-fresh", "p-published"})
        self.assertEqual({r[0] for r in self.conn.execute("SELECT id FROM ai_presentation_videos")}, {"v-published"})
        self.assertIn("k/p-old-draft", self.deleted)
        self.assertIn("k/p-old-approved", self.deleted)
        self.assertIn("k/v-old", self.deleted)
        self.assertNotIn("k/p-published", self.deleted)
        self.assertNotIn("k/v-published", self.deleted)
        self.assertEqual((summary["presentations"], summary["videos"]), (2, 1))

    def test_deck_behind_a_kept_video_is_not_removed(self):
        self._pres("p-source", "draft", OLD)
        self._video("v-published", "published", OLD, pres="p-source")
        retention.purge_expired(now=NOW, hours=24, paths=object(), storage_runtime=FakeRuntime())
        self.assertEqual(self._count("ai_presentations"), 1)
        self.assertNotIn("k/p-source", self.deleted)

    def test_shared_storage_object_is_not_deleted_while_another_row_uses_it(self):
        self._pres("p-a", "draft", OLD, key="shared/key")
        self._pres("p-b", "published", OLD, key="shared/key")
        retention.purge_expired(now=NOW, hours=24, paths=object(), storage_runtime=FakeRuntime())
        self.assertEqual({r[0] for r in self.conn.execute("SELECT id FROM ai_presentations")}, {"p-b"})
        self.assertNotIn("shared/key", self.deleted)

    def test_storage_failure_keeps_row_for_next_run(self):
        self._pres("p-old", "draft", OLD)
        with patch.object(retention, "_delete_artifact", side_effect=RuntimeError("r2 down")):
            summary = retention.purge_expired(now=NOW, hours=24, paths=object(), storage_runtime=FakeRuntime())
        self.assertEqual(self._count("ai_presentations"), 1)
        self.assertEqual(summary["errors"], 1)

    def test_unapproved_drafts_and_old_jobs_go_approved_scripts_stay(self):
        def script(sid, status, updated, pub="", job=""):
            self.conn.execute(
                "INSERT INTO media_scripts(id,material_id,group_key,training_area,title,body,status,source_job_id,"
                "draft_type,publication_material_id,created_by,updated_by,approved_by,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (sid, "m", "g", "a", sid, "b", status, job, "script", pub, "u", "u", "", updated, updated))
        script("s-old-draft", "draft", OLD)
        script("s-fresh-draft", "draft", FRESH)
        script("s-approved", "approved", OLD, job="job-kept")
        script("s-published-outline", "draft", OLD, pub="mat-1")
        for jid, updated in (("job-old", OLD), ("job-kept", OLD), ("job-fresh", FRESH)):
            self.conn.execute(
                "INSERT INTO media_script_jobs(id,material_id,group_key,training_area,actor_username,status,request_json,"
                "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (jid, "m", "g", "a", "u", "completed", "{}", updated, updated))
        self.conn.commit()
        retention.purge_expired(now=NOW, hours=24, paths=object(), storage_runtime=FakeRuntime())
        self.assertEqual({r[0] for r in self.conn.execute("SELECT id FROM media_scripts")},
                         {"s-fresh-draft", "s-approved", "s-published-outline"})
        self.assertEqual({r[0] for r in self.conn.execute("SELECT id FROM media_script_jobs")}, {"job-kept", "job-fresh"})

    def test_only_old_unlinked_authoring_sources_are_deleted(self):
        local_old = (NOW.astimezone() - dt.timedelta(hours=30)).strftime("%Y-%m-%d %H:%M")
        local_new = (NOW.astimezone() - dt.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")

        def material(mid, active, course, added, desc="", meta="{}"):
            self.conn.execute(
                "INSERT INTO materials(id,filename,title,description,course_id,folder,date_added,storage_filename,"
                "storage_meta,active) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (mid, "f", "t", desc, course, mid, added, "s", meta, active))
        material("src-old", 0, "", local_old, meta='{"authoringOnly": true}')
        material("src-legacy", 0, "", local_old, desc="AI 講稿私人來源；教師核准前不提供學員使用。")
        material("src-new", 0, "", local_new, meta='{"authoringOnly": true}')
        material("draft-course-material", 0, "course-1", local_old, desc="課程草稿教材")
        material("published", 1, "", local_old, desc="AI 講稿私人來源")
        self.conn.commit()
        removed = []
        with patch("teacher_app.materials.service.delete_material", side_effect=lambda mid, **kw: removed.append(mid)):
            summary = retention.purge_expired(now=NOW, hours=24, paths=object(), storage_runtime=FakeRuntime())
        self.assertEqual(sorted(removed), ["src-legacy", "src-old"])
        self.assertEqual(summary["sources"], 2)


if __name__ == "__main__":
    unittest.main()
