"""Approved lecture scripts: keep the in-use version plus one previous version (2026-10-10)."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask, g

from teacher_app.common import db as common_db
from teacher_app.maintenance.ai_material_migration import ai_material_drafts_97
from teacher_app.maintenance.media_audio_migration import media_audio_jobs_95
from teacher_app.maintenance.media_script_migration import media_script_jobs_94
from teacher_app.materials import media_script_repository as repo
from teacher_app.materials.media_script_routes import register_media_script_routes

ROOT = Path(__file__).resolve().parents[1]
BODY = "講稿內容" * 30


class RetentionRepositoryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "teacher.db"
        conn = sqlite3.connect(self.db_path)
        media_script_jobs_94(conn, "sqlite")
        media_audio_jobs_95(conn, "sqlite")
        ai_material_drafts_97(conn, "sqlite")
        conn.commit()
        conn.close()
        patcher = patch.object(common_db, "sqlite_path", return_value=self.db_path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def _script(self, title, *, material="mat-1", draft_type="script", user="t1", approve=False):
        script = repo.create_script(
            material_id=material, group_key="grpBio", training_area="internal", title=title, body=BODY,
            source_job_id="job", source_chunks=[], actor_username=user, draft_type=draft_type,
        )
        if approve:
            repo.update_script(script["id"], title=title, body=BODY, status="approved", actor_username=user)
        return script["id"]

    def _statuses(self, material="mat-1"):
        return {row["title"]: row["status"] for row in repo.list_drafts(material)}

    def test_keeps_newest_two_and_removes_older_approved_versions(self):
        for name in ("v1", "v2", "v3"):
            self._script(name, approve=True)
        newest = self._script("v4", approve=True)
        result = repo.enforce_approval_retention("mat-1", newest)
        self.assertEqual(self._statuses(), {"v4": "approved", "v3": "superseded"})
        self.assertEqual({item["title"] for item in result["deleted"]}, {"v1", "v2"})
        self.assertEqual([item["title"] for item in result["superseded"]], ["v3"])

    def test_drafts_other_materials_and_other_draft_types_are_never_touched(self):
        self._script("old", approve=True)
        self._script("a-draft")
        self._script("handout", draft_type="handout", approve=True)
        self._script("other-material", material="mat-2", approve=True)
        newest = self._script("new", approve=True)
        repo.enforce_approval_retention("mat-1", newest)
        statuses = self._statuses()
        self.assertEqual(statuses["a-draft"], "draft")
        self.assertEqual(statuses["handout"], "approved")
        self.assertEqual(statuses["old"], "superseded")
        self.assertEqual(self._statuses("mat-2"), {"other-material": "approved"})

    def test_script_needed_by_an_active_narration_job_is_not_deleted(self):
        oldest = self._script("v1", approve=True)
        self._script("v2", approve=True)
        newest = self._script("v3", approve=True)
        conn = sqlite3.connect(self.db_path)
        columns = [row[1] for row in conn.execute("PRAGMA table_info(media_audio_jobs)")]
        values = {"id": "job-1", "script_id": oldest, "material_id": "mat-1", "group_key": "grpBio",
                  "training_area": "internal", "actor_username": "t1", "status": "queued", "request_json": "{}"}
        row = {name: values.get(name, "") for name in columns}
        for name in columns:
            if name in {"attempts", "progress_percent"}:
                row[name] = 0
        conn.execute(
            f"INSERT INTO media_audio_jobs({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
            [row[name] for name in columns],
        )
        conn.commit()
        conn.close()
        result = repo.enforce_approval_retention("mat-1", newest)
        self.assertEqual([item["id"] for item in result["protected"]], [oldest])
        self.assertIn("v1", self._statuses())
        # Once nothing needs it any more, the next run removes it.
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE media_audio_jobs SET status='completed'")
        conn.commit()
        conn.close()
        repo.enforce_approval_retention("mat-1", newest)
        self.assertNotIn("v1", self._statuses())

    def test_default_newest_is_the_latest_approval_and_cleanup_is_idempotent(self):
        for name in ("v1", "v2", "v3"):
            self._script(name, approve=True)
        repo.enforce_approval_retention("mat-1")
        again = repo.enforce_approval_retention("mat-1")
        self.assertEqual(self._statuses(), {"v3": "approved", "v2": "superseded"})
        self.assertEqual(again["deleted"], [])
        self.assertEqual(repo.enforce_approval_retention("no-material")["current"], "")

    def test_cleanup_own_drafts_only_removes_my_unapproved_drafts(self):
        keep_active = self._script("active")
        self._script("mine")
        self._script("theirs", user="t2")
        self._script("approved", approve=True)
        removed = repo.cleanup_own_drafts("mat-1", "t1", except_id=keep_active)
        self.assertEqual([item["title"] for item in removed], ["mine"])
        self.assertEqual(set(self._statuses()), {"active", "theirs", "approved"})


class RetentionRouteTests(unittest.TestCase):
    def _app(self):
        app = Flask(__name__)
        app.secret_key = "test"

        @app.before_request
        def bind_user():
            g.teacher_user = {"username": "t1", "role": "clinical_teacher", "roles": ["clinical_teacher"],
                              "preferredGroup": "grpBio"}

        register_media_script_routes(app)
        return app

    def test_approval_applies_retention_and_audits_each_removed_version(self):
        current = {"id": "s4", "materialId": "mat-1", "group": "grpBio", "draftType": "script",
                   "title": "v4", "status": "draft", "body": BODY}
        updated = dict(current, status="approved", approvedBy="t1")
        retention = {"current": "s4",
                     "superseded": [{"id": "s3", "title": "v3", "status": "approved"}],
                     "deleted": [{"id": "s2", "title": "v2", "status": "superseded"}], "protected": []}
        module = "teacher_app.materials.media_script_routes"
        with self._app().test_client() as client, \
             patch(f"{module}.media_script_repository.get_script", return_value=current), \
             patch(f"{module}.media_script_repository.update_script", return_value=updated), \
             patch(f"{module}.media_script_repository.enforce_approval_retention", return_value=retention) as enforce, \
             patch(f"{module}.audit.record_event") as record:
            response = client.patch("/api/media-scripts/s4", json={"body": BODY, "status": "approved"})
        self.assertEqual(response.status_code, 200)
        enforce.assert_called_once_with("mat-1", "s4")
        self.assertEqual(response.get_json()["retention"],
                         {"kept": 2, "superseded": 1, "deleted": 1, "protected": 0})
        actions = [call.kwargs["action"] for call in record.call_args_list]
        self.assertEqual(actions, ["media.script.approve", "media.script.supersede", "media.script.retention_delete"])

    def test_saving_a_draft_does_not_trigger_retention(self):
        current = {"id": "s1", "materialId": "mat-1", "group": "grpBio", "draftType": "script",
                   "title": "t", "status": "draft", "body": BODY}
        module = "teacher_app.materials.media_script_routes"
        with self._app().test_client() as client, \
             patch(f"{module}.media_script_repository.get_script", return_value=current), \
             patch(f"{module}.media_script_repository.update_script", return_value=current), \
             patch(f"{module}.media_script_repository.enforce_approval_retention") as enforce, \
             patch(f"{module}.audit.record_event"):
            response = client.patch("/api/media-scripts/s1", json={"body": BODY, "status": "draft"})
        self.assertEqual(response.status_code, 200)
        enforce.assert_not_called()
        self.assertNotIn("retention", response.get_json())

    def test_superseded_history_version_is_read_only(self):
        history = {"id": "s3", "materialId": "mat-1", "group": "grpBio", "draftType": "script",
                   "title": "v3", "status": "superseded", "body": BODY}
        module = "teacher_app.materials.media_script_routes"
        with self._app().test_client() as client, \
             patch(f"{module}.media_script_repository.get_script", return_value=history), \
             patch(f"{module}.media_script_repository.update_script") as update:
            response = client.patch("/api/media-scripts/s3", json={"body": BODY, "status": "approved"})
        self.assertEqual(response.status_code, 409)
        update.assert_not_called()

    def test_cleanup_endpoint_is_group_scoped_and_validates_mode(self):
        module = "teacher_app.materials.media_script_routes"
        other = {"id": "mat-1", "group": "grpBB"}
        own = {"id": "mat-1", "group": "grpBio"}
        with self._app().test_client() as client, \
             patch(f"{module}.material_repository.get_material", return_value=other), \
             patch(f"{module}.media_script_repository.enforce_approval_retention") as enforce:
            denied = client.post("/api/media-scripts/cleanup", json={"materialId": "mat-1", "mode": "versions"})
        self.assertEqual(denied.status_code, 403)
        enforce.assert_not_called()
        with self._app().test_client() as client, \
             patch(f"{module}.material_repository.get_material", return_value=own):
            bad = client.post("/api/media-scripts/cleanup", json={"materialId": "mat-1", "mode": "everything"})
        self.assertEqual(bad.status_code, 400)
        with self._app().test_client() as client, \
             patch(f"{module}.material_repository.get_material", return_value=own), \
             patch(f"{module}.media_script_repository.cleanup_own_drafts",
                   return_value=[{"id": "d1", "title": "x", "status": "draft"}]) as cleanup, \
             patch(f"{module}.audit.record_event") as record:
            ok = client.post("/api/media-scripts/cleanup",
                             json={"materialId": "mat-1", "mode": "drafts", "exceptId": "keep"})
        self.assertEqual(ok.get_json()["deletedDrafts"], 1)
        cleanup.assert_called_once_with("mat-1", "t1", except_id="keep")
        self.assertEqual(record.call_args.kwargs["action"], "media.script.discard")

    def test_in_flight_narration_job_may_finish_with_a_superseded_script(self):
        source = (ROOT / "teacher_app/materials/media_audio_jobs.py").read_text(encoding="utf-8")
        self.assertIn('not in {"approved", "superseded"}', source)
        # Starting a new narration still requires an approved script.
        self.assertIn('str(script.get("status") or "") != "approved"', source)


if __name__ == "__main__":
    unittest.main()
