import datetime as dt
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as appmod
import pgy_app
import schema_migrations


class R2FreeBudgetGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / "r2-guard.sqlite"
        self.patcher = patch.object(appmod, "_db_conn", self.connect)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        appmod.init_material_jobs_db()
        conn, kind = self.connect()
        try:
            schema_migrations._b_free_local_worker_67(conn, kind)
            schema_migrations.ensure_r2_free_budget_guard_67(appmod)
        finally:
            conn.close()

    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, "sqlite"

    def scalar(self, sql, args=()):
        conn, _ = self.connect()
        try:
            return conn.execute(sql, args).fetchone()[0]
        finally:
            conn.close()

    def test_env_parser_falls_back_and_bounds(self):
        self.assertEqual(appmod._bounded_env_number("__MISSING_R2_TEST__", 10, 1, 20), 10)
        with patch.dict("os.environ", {"__R2_BAD_TEST__": "not-a-number"}):
            self.assertEqual(appmod._bounded_env_number("__R2_BAD_TEST__", 10, 1, 20), 10)
        with patch.dict("os.environ", {"__R2_BOUND_TEST__": "999"}):
            self.assertEqual(appmod._bounded_env_number("__R2_BOUND_TEST__", 10, 1, 20), 20)

    def test_threshold_levels_cover_60_80_90(self):
        with patch.object(appmod, "R2_WARNING_PERCENT", 60), patch.object(appmod, "R2_UPLOAD_BLOCK_PERCENT", 80), patch.object(appmod, "R2_EMERGENCY_PERCENT", 90):
            self.assertEqual(appmod._r2_budget_level(59.9), "green")
            self.assertEqual(appmod._r2_budget_level(60), "warning")
            self.assertEqual(appmod._r2_budget_level(80), "blocked")
            self.assertEqual(appmod._r2_budget_level(90), "emergency")

    def test_reservation_is_atomic_and_counts_reserved_bytes(self):
        with patch.object(appmod, "FREE_ONLY_MODE", False):
            appmod.reserve_r2_upload("one", "_staging/one", 120 * 1024 * 1024)
            with self.assertRaises(sqlite3.IntegrityError):
                appmod.reserve_r2_upload("one", "_staging/one", 120 * 1024 * 1024)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM r2_upload_reservations WHERE status='active'"), 1)
        self.assertEqual(appmod.r2_budget_status()["reservedBytes"], 120 * 1024 * 1024)

    def test_hard_staging_limit_includes_existing_and_reservations(self):
        with patch.object(appmod, "FREE_ONLY_MODE", False), patch.object(appmod, "R2_STAGING_MAX_CURRENT_GB", 0.1):
            appmod.r2_record_object("_staging/existing", 80 * 1024 * 1024)
            with self.assertRaisesRegex(ValueError, "8GB"):
                appmod.reserve_r2_upload("over", "_staging/over", 30 * 1024 * 1024)

    def test_large_guard_blocks_but_small_file_bypasses_it(self):
        blocked = {"level": "blocked"}
        with patch.object(appmod, "MATERIAL_R2_LARGE_FILE_MB", 100), patch.object(appmod, "r2_budget_status", return_value=blocked), patch.object(appmod, "cleanup_r2_budget_state"):
            appmod.enforce_r2_large_upload_budget("small", "_staging/small", 99 * 1024 * 1024)
            with self.assertRaisesRegex(ValueError, "安全門檻"):
                appmod.enforce_r2_large_upload_budget("large", "_staging/large", 100 * 1024 * 1024)

    def test_release_on_abort_and_expired_multipart_cleanup(self):
        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=7)).isoformat()
        conn, _ = self.connect()
        try:
            conn.execute("INSERT INTO material_upload_sessions(id,job_id,material_id,staging_key,original_name,source_sha256,source_bytes,r2_upload_id,part_size,expected_parts,payload,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", ("expired", "job-expired", "m", "_staging/expired", "movie.mp4", "a" * 64, 200, "remote", 8, 1, "{}", "uploading", old, old))
        finally:
            conn.close()
        with patch.object(appmod, "FREE_ONLY_MODE", False):
            appmod.reserve_r2_upload("expired", "_staging/expired", 200)
        class R2:
            def abort_multipart_upload(self, **_kwargs): return {}
        with patch.object(appmod, "r2_client", return_value=R2()), patch.object(appmod, "R2_MULTIPART_ABANDON_HOURS", 6):
            self.assertEqual(appmod.cleanup_r2_budget_state(), 1)
        self.assertEqual(self.scalar("SELECT status FROM material_upload_sessions WHERE id='expired'"), "expired")
        self.assertEqual(self.scalar("SELECT status FROM r2_upload_reservations WHERE upload_id='expired'"), "released")

    def test_failed_retention_and_cleanup_pending(self):
        appmod.create_material_job(job_id="failed", payload={}, staging_backend="r2", staging_key="_staging/failed", source_sha256="a" * 64, source_bytes=1, material_id="m")
        conn, _ = self.connect()
        try:
            old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=25)).isoformat()
            conn.execute("UPDATE material_jobs SET status='failed',updated_at=? WHERE id='failed'", (old,))
        finally:
            conn.close()
        with patch.object(appmod, "R2_STAGING_FAILED_RETENTION_HOURS", 24), patch.object(appmod, "delete_material_job_staging", side_effect=RuntimeError("temporary")):
            appmod.cleanup_material_job_staging()
        self.assertEqual(self.scalar("SELECT cleanup_pending FROM material_jobs WHERE id='failed'"), 1)

    def test_gb_month_is_teacher_estimate_and_status_has_no_credentials(self):
        now = dt.datetime(2026, 9, 15, tzinfo=dt.timezone.utc)
        start, _ = appmod._r2_month_bounds(now)
        appmod.r2_record_object("materials/object", 10 * appmod._R2_GB)
        conn, _ = self.connect()
        try:
            conn.execute("UPDATE r2_usage_ledger SET uploaded_at=? WHERE object_key='materials/object'", (start.isoformat(),))
            estimated = appmod._r2_estimated_gb_month(conn, now)
        finally:
            conn.close()
        self.assertGreater(estimated, 4.0)
        status = appmod.r2_budget_status()
        self.assertTrue(status["estimatedOnly"])
        self.assertNotIn("secret", str(status).lower())
        self.assertNotIn("access_key", str(status).lower())

    def test_0067_applied_compatibility_ensure_is_idempotent(self):
        conn, _ = self.connect()
        try:
            conn.execute("CREATE TABLE schema_migrations(version TEXT PRIMARY KEY,applied_at TEXT NOT NULL)")
            conn.execute("INSERT INTO schema_migrations VALUES('0067-b-free-local-worker','old')")
        finally:
            conn.close()
        schema_migrations.ensure_r2_free_budget_guard_67(appmod)
        schema_migrations.ensure_r2_free_budget_guard_67(appmod)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name IN ('r2_upload_reservations','r2_usage_ledger')"), 2)

    def test_postgres_path_uses_safe_advisory_transaction_and_boolean_schema(self):
        source = Path(appmod.__file__).read_text(encoding="utf-8")
        migration = Path(schema_migrations.__file__).read_text(encoding="utf-8")
        self.assertIn("pg_advisory_xact_lock", source)
        self.assertIn("BOOLEAN", migration)
        self.assertIn("ensure_r2_free_budget_guard_67", migration)

    def test_admin_status_is_protected_and_health_is_not_budget_gated(self):
        client = pgy_app.app.test_client()
        self.assertIn(client.get("/api/material-jobs").status_code, {401, 403, 503})
        baseline = client.get("/health").status_code
        with patch.object(appmod, "r2_budget_status", return_value={"level": "emergency"}):
            health = client.get("/health")
        self.assertEqual(health.status_code, baseline)


if __name__ == "__main__":
    unittest.main()
