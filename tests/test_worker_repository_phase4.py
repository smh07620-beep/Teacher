"""Phase 4 regressions for canonical worker queue/session groundwork."""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import sqlite3
import tempfile
import unittest
from pathlib import Path

from teacher_app.maintenance import migrations
from teacher_app.worker import protocol
from teacher_app.worker import repository
from teacher_app.worker import operations


class WorkerRepositoryPhase4Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "worker.sqlite"
        conn, _kind = self.connect()
        try:
            conn.executescript(
                """
                CREATE TABLE material_jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'queued',
                    priority INTEGER NOT NULL DEFAULT 50,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    available_at TEXT NOT NULL,
                    started_at TEXT NOT NULL DEFAULT '',
                    finished_at TEXT NOT NULL DEFAULT '',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    stage TEXT NOT NULL DEFAULT '等待處理',
                    detail TEXT NOT NULL DEFAULT '',
                    payload TEXT NOT NULL DEFAULT '{}',
                    staging_path TEXT NOT NULL DEFAULT '',
                    staging_backend TEXT NOT NULL DEFAULT 'local',
                    staging_key TEXT NOT NULL DEFAULT '',
                    original_name TEXT NOT NULL DEFAULT '',
                    material_id TEXT NOT NULL DEFAULT '',
                    source_sha256 TEXT NOT NULL DEFAULT '',
                    source_bytes INTEGER NOT NULL DEFAULT 0,
                    error TEXT NOT NULL DEFAULT '',
                    result TEXT NOT NULL DEFAULT '{}',
                    worker_id TEXT NOT NULL DEFAULT '',
                    worker_last_seen TEXT NOT NULL DEFAULT '',
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    cleanup_pending INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX idx_material_jobs_queue
                    ON material_jobs(status, priority, created_at);
                CREATE TABLE material_worker_heartbeats (
                    worker_id TEXT PRIMARY KEY,
                    last_seen TEXT NOT NULL,
                    capabilities TEXT NOT NULL DEFAULT '{}',
                    current_job_id TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE material_upload_sessions (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL UNIQUE,
                    material_id TEXT NOT NULL,
                    staging_key TEXT NOT NULL,
                    original_name TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    source_bytes INTEGER NOT NULL,
                    r2_upload_id TEXT NOT NULL,
                    part_size INTEGER NOT NULL,
                    expected_parts INTEGER NOT NULL,
                    payload TEXT NOT NULL DEFAULT '{}',
                    completed_parts TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
        finally:
            conn.close()

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, "sqlite"

    def job(self, job_id="job-1", *, created="2026-09-18T10:00:00+00:00"):
        return {
            "id": job_id,
            "status": "queued",
            "priority": 50,
            "created_at": created,
            "updated_at": created,
            "available_at": created,
            "max_attempts": 3,
            "stage": "等待背景處理",
            "detail": "queued",
            "payload": {"originalName": "lesson.txt", "title": "Lesson"},
            "staging_path": "",
            "staging_backend": "r2",
            "staging_key": f"_staging/{job_id}/source.txt",
            "original_name": "lesson.txt",
            "material_id": f"material-{job_id}",
            "source_sha256": "a" * 64,
            "source_bytes": 42,
        }

    def session(self, upload_id="upload-1", job_id="job-upload-1"):
        stamp = "2026-09-18T10:00:00+00:00"
        return {
            "id": upload_id,
            "job_id": job_id,
            "material_id": f"material-{job_id}",
            "staging_key": f"_staging/{job_id}/source.mp4",
            "original_name": "movie.mp4",
            "source_sha256": "b" * 64,
            "source_bytes": 16,
            "r2_upload_id": f"remote-{upload_id}",
            "part_size": 8,
            "expected_parts": 2,
            "payload": {"originalName": "movie.mp4", "title": "Movie"},
            "completed_parts": [],
            "status": "uploading",
            "created_at": stamp,
            "updated_at": stamp,
        }

    def test_row_decode_and_queue_reads_preserve_payload_contract(self):
        repository.create_material_job(self.job(), connection_factory=self.connect)
        full = repository.get_material_job(
            "job-1", include_payload=True, connection_factory=self.connect
        )
        public = repository.list_material_jobs(connection_factory=self.connect)[0]
        self.assertEqual(full["payload"]["originalName"], "lesson.txt")
        self.assertEqual(full["originalName"], "lesson.txt")
        self.assertEqual(full["stagingBackend"], "r2")
        self.assertEqual(full["sourceBytes"], 42)
        self.assertNotIn("payload", public)
        self.assertEqual(public["title"], "Lesson")

    def test_sqlite_atomic_claim_allows_only_one_worker(self):
        repository.create_material_job(self.job(), connection_factory=self.connect)

        def claim(worker_id):
            return repository.claim_next_material_job(
                worker_id,
                now="2026-09-18T11:00:00+00:00",
                connection_factory=self.connect,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(claim, ("worker-a", "worker-b")))
        winners = [result for result in results if result]
        self.assertEqual(len(winners), 1)
        self.assertEqual(winners[0]["status"], "processing")
        self.assertEqual(winners[0]["attempts"], 1)
        stored = repository.get_material_job(
            "job-1", include_payload=True, connection_factory=self.connect
        )
        self.assertEqual(stored["workerId"], winners[0]["workerId"])

    def test_owned_transition_and_stale_snapshot_are_compare_and_set(self):
        repository.create_material_job(self.job(), connection_factory=self.connect)
        claimed = repository.claim_next_material_job(
            "worker-a",
            now="2026-09-18T11:00:00+00:00",
            connection_factory=self.connect,
        )
        self.assertIsNotNone(claimed)
        stale = repository.list_stale_processing_jobs(
            "2026-09-18T11:30:00+00:00", connection_factory=self.connect
        )[0]

        denied = repository.transition_owned_material_job(
            "job-1",
            "worker-b",
            fields={"status": "failed", "updated_at": "2026-09-18T11:05:00+00:00"},
            connection_factory=self.connect,
        )
        self.assertIsNone(denied)

        self.assertTrue(
            repository.touch_owned_material_job(
                "job-1",
                "worker-a",
                seen_at="2026-09-18T11:20:00+00:00",
                connection_factory=self.connect,
            )
        )
        stale_loss = repository.cas_material_job(
            "job-1",
            expected_statuses=("processing",),
            expected_updated_at=stale["updatedAt"],
            fields={"status": "queued", "updated_at": "2026-09-18T11:30:00+00:00"},
            connection_factory=self.connect,
        )
        self.assertIsNone(stale_loss)

        completed = repository.transition_owned_material_job(
            "job-1",
            "worker-a",
            fields={
                "status": "completed",
                "finished_at": "2026-09-18T11:21:00+00:00",
                "updated_at": "2026-09-18T11:21:00+00:00",
            },
            connection_factory=self.connect,
        )
        self.assertEqual(completed["status"], "completed")
        self.assertIsNone(
            repository.transition_owned_material_job(
                "job-1",
                "worker-a",
                fields={"status": "failed"},
                connection_factory=self.connect,
            )
        )

    def test_canonical_stale_recovery_requeues_or_fails_and_clears_owner(self):
        stale = self.job("stale-ok", created="2026-09-18T09:00:00+00:00")
        stale.update({"status": "processing", "worker_id": "worker-a", "worker_last_seen": "2026-09-18T09:05:00+00:00"})
        repository.create_material_job(stale, connection_factory=self.connect)
        missing = self.job("stale-missing", created="2026-09-18T09:00:00+00:00")
        missing.update({"status": "processing", "worker_id": "worker-b", "worker_last_seen": "2026-09-18T09:05:00+00:00"})
        repository.create_material_job(missing, connection_factory=self.connect)

        recovered = operations.recover_stale_processing_jobs(
            lambda job: job["id"] == "stale-ok",
            stale_seconds=300,
            now=dt.datetime(2026, 9, 18, 11, 0, tzinfo=dt.timezone.utc),
            connection_factory=self.connect,
        )
        self.assertEqual(recovered, {"requeued": 1, "failed": 1, "lostRace": 0})
        queued = repository.get_material_job("stale-ok", include_payload=True, connection_factory=self.connect)
        failed = repository.get_material_job("stale-missing", include_payload=True, connection_factory=self.connect)
        self.assertEqual(queued["status"], "queued")
        self.assertEqual(queued["workerId"], "")
        self.assertEqual(queued["workerLastSeen"], "")
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["workerId"], "")

    def test_canonical_stale_recovery_loses_to_fresh_heartbeat(self):
        stale = self.job("stale-race", created="2026-09-18T09:00:00+00:00")
        stale.update({"status": "processing", "worker_id": "worker-a", "worker_last_seen": "2026-09-18T09:05:00+00:00"})
        repository.create_material_job(stale, connection_factory=self.connect)

        def staging_exists(job):
            self.assertEqual(job["workerId"], "worker-a")
            self.assertTrue(
                repository.touch_owned_material_job(
                    "stale-race",
                    "worker-a",
                    seen_at="2026-09-18T10:59:59+00:00",
                    connection_factory=self.connect,
                )
            )
            return True

        recovered = operations.recover_stale_processing_jobs(
            staging_exists,
            stale_seconds=300,
            now=dt.datetime(2026, 9, 18, 11, 0, tzinfo=dt.timezone.utc),
            connection_factory=self.connect,
        )
        self.assertEqual(recovered, {"requeued": 0, "failed": 0, "lostRace": 1})
        current = repository.get_material_job("stale-race", include_payload=True, connection_factory=self.connect)
        self.assertEqual(current["status"], "processing")
        self.assertEqual(current["workerId"], "worker-a")
        self.assertEqual(current["updatedAt"], "2026-09-18T10:59:59+00:00")

    def test_0079_publish_receipt_migration_is_additive_on_sqlite_and_postgres(self):
        conn, kind = self.connect()
        try:
            migrations._provider_publish_receipts_79(conn, kind)
            migrations._provider_publish_receipts_79(conn, kind)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(material_publish_receipts)").fetchall()}
        finally:
            conn.close()
        self.assertTrue({"job_id", "publish_key", "source_sha256", "backend", "worker_id", "result", "published_at"}.issubset(columns))

        class Recorder:
            def __init__(self): self.calls = []
            def execute(self, sql, params=()):
                self.calls.append((sql, tuple(params)))
                return self
            def fetchall(self): return []

        recorder = Recorder()
        migrations._provider_publish_receipts_79(recorder, "postgres")
        sql = "\n".join(statement for statement, _params in recorder.calls)
        self.assertIn("material_publish_receipts", sql)
        self.assertIn("result JSONB NOT NULL DEFAULT '{}'::jsonb", sql)

    def test_admin_cancel_snapshot_cannot_overwrite_a_concurrent_claim(self):
        repository.create_material_job(self.job(), connection_factory=self.connect)
        queued = repository.get_material_job(
            "job-1", include_payload=True, connection_factory=self.connect
        )
        claimed = repository.claim_next_material_job(
            "worker-a",
            now="2026-09-18T11:00:00+00:00",
            connection_factory=self.connect,
        )
        self.assertEqual(claimed["status"], "processing")

        cancelled = repository.cas_material_job(
            "job-1",
            expected_statuses=("queued", "retry_wait"),
            expected_updated_at=queued["updatedAt"],
            fields={
                "status": "cancelled",
                "cancel_requested": True,
                "updated_at": "2026-09-18T11:01:00+00:00",
            },
            connection_factory=self.connect,
        )
        self.assertIsNone(cancelled)
        current = repository.get_material_job(
            "job-1", include_payload=True, connection_factory=self.connect
        )
        self.assertEqual(current["status"], "processing")
        self.assertEqual(current["workerId"], "worker-a")

    def test_queue_aggregates_candidates_and_heartbeat_reads_are_canonical(self):
        repository.create_material_job(self.job("queued"), connection_factory=self.connect)
        failed = self.job("failed", created="2026-09-18T09:00:00+00:00")
        failed["status"] = "failed"
        repository.create_material_job(failed, connection_factory=self.connect)
        repository.upsert_heartbeat(
            "worker-a",
            last_seen="2026-09-18T11:00:00+00:00",
            capabilities={"ffmpeg": {"available": True}},
            current_job_id="queued",
            connection_factory=self.connect,
        )
        aggregates = repository.queue_aggregates(connection_factory=self.connect)
        self.assertEqual(aggregates["queued"]["count"], 1)
        self.assertEqual(aggregates["failed"]["count"], 1)
        repository.update_material_job(
            "failed",
            fields={"cleanup_pending": True},
            connection_factory=self.connect,
        )
        self.assertEqual(
            repository.count_cleanup_pending_jobs(connection_factory=self.connect), 1
        )
        self.assertEqual(
            repository.list_cleanup_candidates(connection_factory=self.connect)[0]["id"],
            "failed",
        )
        heartbeat = repository.list_heartbeats(connection_factory=self.connect)[0]
        self.assertTrue(heartbeat["capabilities"]["ffmpeg"]["available"])

    def test_upload_session_cas_prevents_double_terminal_transition(self):
        repository.create_upload_session(self.session(), connection_factory=self.connect)
        self.assertEqual(
            repository.upload_session_status_counts(connection_factory=self.connect),
            {"uploading": 1},
        )
        first = repository.cas_upload_session_status(
            "upload-1",
            expected_status="uploading",
            new_status="aborted",
            updated_at="2026-09-18T11:00:00+00:00",
            connection_factory=self.connect,
        )
        second = repository.cas_upload_session_status(
            "upload-1",
            expected_status="uploading",
            new_status="expired",
            updated_at="2026-09-18T11:01:00+00:00",
            connection_factory=self.connect,
        )
        self.assertEqual(first["status"], "aborted")
        self.assertIsNone(second)
        self.assertEqual(
            repository.upload_session_status_counts(connection_factory=self.connect),
            {"aborted": 1},
        )

    def test_finalize_upload_session_and_job_is_atomic_and_single_winner(self):
        repository.create_upload_session(self.session(), connection_factory=self.connect)
        job = self.job("job-upload-1")
        parts = [
            {"PartNumber": 1, "ETag": "etag-1"},
            {"PartNumber": 2, "ETag": "etag-2"},
        ]

        def finalize(_index):
            return repository.finalize_upload_session_with_job(
                "upload-1",
                completed_parts=parts,
                updated_at="2026-09-18T11:00:00+00:00",
                job=job,
                connection_factory=self.connect,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(finalize, (1, 2)))
        self.assertEqual(len([result for result in results if result]), 1)
        session = repository.get_upload_session("upload-1", connection_factory=self.connect)
        self.assertEqual(session["status"], "completed")
        self.assertEqual(session["completed_parts"], parts)
        conn, _kind = self.connect()
        try:
            jobs = conn.execute(
                "SELECT COUNT(*) FROM material_jobs WHERE id='job-upload-1'"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(jobs, 1)

    def test_finalize_insert_failure_rolls_back_session_status(self):
        repository.create_upload_session(
            self.session("upload-conflict", "job-conflict"),
            connection_factory=self.connect,
        )
        repository.create_material_job(
            self.job("job-conflict"), connection_factory=self.connect
        )
        with self.assertRaises(sqlite3.IntegrityError):
            repository.finalize_upload_session_with_job(
                "upload-conflict",
                completed_parts=[{"PartNumber": 1, "ETag": "etag-1"}],
                updated_at="2026-09-18T11:00:00+00:00",
                job=self.job("job-conflict"),
                connection_factory=self.connect,
            )
        session = repository.get_upload_session(
            "upload-conflict", connection_factory=self.connect
        )
        self.assertEqual(session["status"], "uploading")
        self.assertEqual(session["completed_parts"], [])


class WorkerProtocolPhase4Tests(unittest.TestCase):
    def test_bearer_token_match_is_strict_and_empty_secret_fails_closed(self):
        self.assertTrue(protocol.bearer_token_matches("secret", "Bearer secret"))
        self.assertFalse(protocol.bearer_token_matches("secret", "Bearer wrong"))
        self.assertFalse(protocol.bearer_token_matches("", "Bearer "))
        self.assertFalse(protocol.bearer_token_matches("secret", "secret"))

    def test_retry_plan_preserves_bounded_legacy_backoff(self):
        retry = protocol.retry_plan(
            2,
            3,
            stamp="2026-09-18T12:00:00+00:00",
        )
        self.assertTrue(retry["retry"])
        self.assertEqual(retry["delaySeconds"], 30)
        self.assertEqual(retry["availableAt"], "2026-09-18T12:00:30+00:00")
        self.assertEqual(
            protocol.retry_plan(3, 3, stamp="2026-09-18T12:00:00+00:00"),
            {"retry": False, "delaySeconds": 0, "availableAt": ""},
        )

    def test_multipart_validation_normalizes_and_rejects_gaps(self):
        parts = protocol.validate_multipart_parts(
            [
                {"partNumber": 1, "etag": "etag-1"},
                {"partNumber": 2, "etag": "etag-2"},
            ],
            2,
        )
        self.assertEqual(
            parts,
            [
                {"PartNumber": 1, "ETag": "etag-1"},
                {"PartNumber": 2, "ETag": "etag-2"},
            ],
        )
        with self.assertRaisesRegex(ValueError, "不完整"):
            protocol.validate_multipart_parts([], 2)
        with self.assertRaisesRegex(ValueError, "格式錯誤"):
            protocol.validate_multipart_parts(
                [{"partNumber": 2, "etag": "etag-2"}], 1
            )

    def test_remote_multipart_parts_and_resume_identity_are_server_safe(self):
        remote = protocol.normalize_remote_multipart_parts(
            [
                {"PartNumber": 3, "ETag": '"etag-3"', "Size": 4},
                {"PartNumber": 1, "ETag": '"etag-1"', "Size": 8},
            ],
            3,
        )
        self.assertEqual([part["PartNumber"] for part in remote], [1, 3])
        self.assertEqual(protocol.missing_multipart_part_numbers(remote, 3), [2])
        with self.assertRaisesRegex(ValueError, "尚未完整"):
            protocol.normalize_remote_multipart_parts(remote, 3, require_complete=True)

        identity = protocol.normalize_client_file_identity(
            filename="movie.mp4",
            size=40,
            last_modified=1700000000000,
            fingerprint="a" * 64,
            strategy="sha256-part-tree-v1",
            part_size=16,
            required=True,
        )
        self.assertTrue(protocol.client_file_identity_matches(identity, dict(identity)))
        changed = {**identity, "fingerprint": "b" * 64}
        self.assertFalse(protocol.client_file_identity_matches(identity, changed))
        with self.assertRaisesRegex(ValueError, "指紋格式"):
            protocol.normalize_client_file_identity(
                filename="movie.mp4",
                size=40,
                last_modified=1700000000000,
                fingerprint="not-a-hash",
                strategy="sha256-part-tree-v1",
                part_size=16,
                required=True,
            )


if __name__ == "__main__":
    unittest.main()
