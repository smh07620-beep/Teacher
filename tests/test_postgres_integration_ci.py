"""Focused real-PostgreSQL integration coverage for CI.

This suite is intentionally skipped during the normal SQLite regression run and
is enabled only by the dedicated PostgreSQL GitHub Actions job.
"""
from __future__ import annotations

import os
import unittest
import uuid

from teacher_app.assessments import ai_job_repository
from teacher_app.assessments import repository as assessment_repository
from teacher_app.auth import accounts
from teacher_app.common import db as common_db
from teacher_app.factory import create_app
from teacher_app.worker import repository as worker_repository


@unittest.skipUnless(os.environ.get("TEACHER_POSTGRES_CI") == "1", "PostgreSQL CI only")
class PostgresIntegrationCiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get("DATABASE_URL", "").startswith("postgres"):
            raise AssertionError("TEACHER_POSTGRES_CI requires a PostgreSQL DATABASE_URL")
        cls.app = create_app()
        cls.app.config.update(TESTING=True)

    def test_fresh_bootstrap_and_required_runtime_tables_exist(self):
        with common_db.read_connection() as (conn, kind):
            self.assertEqual(kind, "postgres")
            names = (
                "schema_migrations",
                "user_accounts",
                "material_jobs",
                "ai_question_jobs",
                "question_versions",
            )
            for name in names:
                row = conn.execute("SELECT to_regclass(%s) AS name", (name,)).fetchone()
                self.assertTrue(dict(row).get("name"), name)

    def test_auth_session_round_trip_uses_postgres(self):
        suffix = uuid.uuid4().hex[:10]
        username = f"ci-{suffix}"
        accounts.create_account(
            {
                "username": username,
                "password": "ci-password-123",
                "name": "CI Admin",
                "empId": f"E-{suffix}",
                "role": "system_admin",
                "roles": ["system_admin"],
                "preferredArea": "internal",
                "preferredGroup": "grpBio",
            }
        )
        client = self.app.test_client()
        response = client.post(
            "/api/auth/login",
            json={"username": username, "password": "ci-password-123"},
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        me = client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        payload = me.get_json()
        self.assertTrue(payload["authenticated"])
        self.assertEqual(payload["user"]["username"], username)

    def test_material_job_repository_round_trip_uses_postgres(self):
        suffix = uuid.uuid4().hex[:10]
        job_id = f"pg-job-{suffix}"
        stamp = "2026-09-21T00:00:00+00:00"
        created = worker_repository.create_material_job(
            {
                "id": job_id,
                "status": "queued",
                "priority": 100,
                "created_at": stamp,
                "updated_at": stamp,
                "available_at": stamp,
                "max_attempts": 3,
                "payload": {"group": "grpBio", "area": "internal", "originalName": "ci.txt"},
                "staging_path": "",
                "staging_backend": "r2",
                "staging_key": f"_staging/{job_id}",
                "original_name": "ci.txt",
                "material_id": f"mat-{suffix}",
                "source_sha256": "a" * 64,
                "source_bytes": 2,
            }
        )
        self.assertEqual(created["id"], job_id)
        loaded = worker_repository.get_material_job(job_id, include_payload=True)
        self.assertEqual(loaded["payload"]["group"], "grpBio")
        self.assertEqual(loaded["stagingBackend"], "r2")

    def test_ai_job_claim_progress_complete_round_trip_uses_postgres(self):
        suffix = uuid.uuid4().hex[:10]
        job_id = f"pg-ai-{suffix}"
        created = ai_job_repository.create_job(
            {
                "id": job_id,
                "quiz_category_id": f"cat-{suffix}",
                "group_key": "grpBio",
                "training_area": "internal",
                "actor_username": f"actor-{suffix}",
                "request": {"materialIds": [f"mat-{suffix}"], "count": 1},
            }
        )
        self.assertEqual(created["status"], "queued")
        claimed = ai_job_repository.claim(job_id, "claim-token")
        self.assertEqual(claimed["status"], "processing")
        self.assertTrue(ai_job_repository.set_progress(job_id, "claim-token", 50, "half", "ci"))
        self.assertTrue(ai_job_repository.complete(job_id, "claim-token", {"ok": True, "questions": []}))
        completed = ai_job_repository.get_job(job_id)
        self.assertEqual(completed["status"], "completed")
        self.assertTrue(completed["result"]["ok"])

    def test_question_version_append_only_store_uses_postgres_jsonb(self):
        suffix = uuid.uuid4().hex[:10]
        question_id = f"q-{suffix}"
        row = {
            "id": question_id,
            "version": 1,
            "quizCategoryId": "",
            "tag": "ci",
            "question": "PostgreSQL CI question?",
            "questionType": "choice",
            "difficulty": "standard",
            "options": ["A", "B"],
            "correct": 0,
            "answerConfig": {},
            "explanation": "CI",
            "tags": ["postgres"],
            "reviewSource": {},
        }
        with common_db.transaction() as (conn, kind):
            self.assertEqual(kind, "postgres")
            inserted = assessment_repository._insert_question_version_on_connection(
                conn,
                kind,
                row,
                created_by="ci",
                change_reason="postgres-ci",
            )
            replay = assessment_repository._insert_question_version_on_connection(
                conn,
                kind,
                row,
                created_by="ci",
                change_reason="postgres-ci",
            )
        self.assertTrue(inserted)
        self.assertFalse(replay)
        versions = assessment_repository.list_question_versions(question_id)
        self.assertEqual(len(versions), 1)
        self.assertEqual(versions[0]["snapshot"]["question"], row["question"])
        self.assertEqual(len(versions[0]["question_hash"]), 64)


if __name__ == "__main__":
    unittest.main()
