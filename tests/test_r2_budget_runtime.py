import datetime as dt
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from teacher_app.maintenance import migrations
from teacher_app.storage import r2_budget, r2_ledger
from teacher_app.worker import repository as worker_repository
from teacher_app.worker import schema as worker_schema


class R2BudgetRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "budget.sqlite"
        conn, kind = self.connect()
        try:
            # 0067 owns the worker/upload-session and R2 budget tables.
            worker_schema.init_schema(conn, kind)
            migrations._b_free_local_worker_67(conn, kind)
            migrations._r2_free_budget_guard_67(conn, kind)
        finally:
            conn.close()
        self.db_patch = patch(
            "teacher_app.common.db.get_connection",
            side_effect=self.connect,
        )
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)

    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, "sqlite"

    def scalar(self, sql, args=()):
        conn, _ = self.connect()
        try:
            return conn.execute(sql, args).fetchone()[0]
        finally:
            conn.close()

    @staticmethod
    def policy(**changes):
        values = dict(
            free_only=False,
            free_storage_gb_month=10.0,
            warning_percent=60,
            upload_block_percent=80,
            emergency_percent=90,
            staging_max_current_gb=8.0,
            failed_retention_hours=24,
            multipart_abandon_hours=6,
            large_file_mb=100,
        )
        values.update(changes)
        return r2_budget.R2BudgetPolicy(**values)

    def test_reservation_is_atomic_and_status_counts_reserved_bytes(self):
        policy = self.policy()
        r2_budget.reserve_upload("one", "_staging/one", 120 * 1024 * 1024, policy=policy)
        with self.assertRaises(sqlite3.IntegrityError):
            r2_budget.reserve_upload("one", "_staging/one", 120 * 1024 * 1024, policy=policy)
        current = r2_budget.status(policy=policy)
        self.assertEqual(current["reservedBytes"], 120 * 1024 * 1024)
        self.assertTrue(current["estimatedOnly"])

    def test_hard_staging_limit_includes_live_ledger_bytes(self):
        policy = self.policy(staging_max_current_gb=0.1)
        r2_ledger.record_object("_staging/existing", 80 * 1024 * 1024)
        with self.assertRaisesRegex(ValueError, "8GB"):
            r2_budget.reserve_upload(
                "over", "_staging/over", 30 * 1024 * 1024, policy=policy
            )

    def test_large_file_guard_bypasses_small_and_blocks_threshold_level(self):
        policy = self.policy(free_only=True, large_file_mb=100)
        with patch.object(r2_budget, "cleanup_budget_state") as cleanup, patch.object(
            r2_budget, "status", return_value={"level": "blocked"}
        ):
            r2_budget.enforce_large_upload_budget(
                "small", "_staging/small", 99 * 1024 * 1024, policy=policy
            )
            cleanup.assert_not_called()
            with self.assertRaisesRegex(ValueError, "安全門檻"):
                r2_budget.enforce_large_upload_budget(
                    "large", "_staging/large", 100 * 1024 * 1024, policy=policy
                )

    def test_cleanup_aborts_stale_multipart_and_releases_reservation(self):
        policy = self.policy(multipart_abandon_hours=6)
        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=7)).isoformat()
        worker_repository.create_upload_session(
            {
                "id": "expired",
                "job_id": "job-expired",
                "material_id": "m",
                "staging_key": "_staging/expired",
                "original_name": "movie.mp4",
                "source_sha256": "a" * 64,
                "source_bytes": 200,
                "r2_upload_id": "remote",
                "part_size": 8,
                "expected_parts": 1,
                "payload": {},
                "completed_parts": [],
                "status": "uploading",
                "created_at": old,
                "updated_at": old,
            }
        )
        r2_budget.reserve_upload("expired", "_staging/expired", 200, policy=policy)

        class R2:
            calls = []

            def abort_multipart_upload(self, **kwargs):
                self.calls.append(kwargs)
                return {}

        client = R2()
        with patch.object(r2_budget.providers, "r2_client", return_value=client), patch.object(
            r2_budget.providers, "R2_BUCKET_NAME", "bucket"
        ):
            self.assertEqual(r2_budget.cleanup_budget_state(policy=policy), 1)
        self.assertEqual(
            worker_repository.get_upload_session("expired")["status"], "expired"
        )
        self.assertEqual(
            self.scalar(
                "SELECT status FROM r2_upload_reservations WHERE upload_id='expired'"
            ),
            "released",
        )
        self.assertEqual(client.calls[0]["Key"], "_staging/expired")

    def test_level_thresholds_match_60_80_90_contract(self):
        policy = self.policy(free_only=True)
        self.assertEqual(r2_budget.budget_level(59.9, policy=policy), "green")
        self.assertEqual(r2_budget.budget_level(60, policy=policy), "warning")
        self.assertEqual(r2_budget.budget_level(80, policy=policy), "blocked")
        self.assertEqual(r2_budget.budget_level(90, policy=policy), "emergency")


if __name__ == "__main__":
    unittest.main()
