import sqlite3
import unittest

from teacher_app.maintenance.material_job_progress_migration import material_job_progress_107
from teacher_app.worker import repository as worker_repository


class MaterialJobProgress0107Tests(unittest.TestCase):
    def test_migration_adds_progress_column_idempotently(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(
                """
                CREATE TABLE material_jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'queued',
                    stage TEXT NOT NULL DEFAULT '等待背景處理'
                )
                """
            )
            material_job_progress_107(conn, "sqlite")
            material_job_progress_107(conn, "sqlite")
            columns = {row[1] for row in conn.execute("PRAGMA table_info(material_jobs)")}
            self.assertIn("progress_percent", columns)
            row = conn.execute(
                "SELECT progress_percent FROM material_jobs WHERE id='missing'"
            ).fetchone()
            self.assertIsNone(row)
        finally:
            conn.close()

    def test_repository_prefers_persisted_progress_but_keeps_legacy_fallback(self):
        persisted = worker_repository.material_job_row_to_dict(
            {
                "id": "job-1",
                "status": "processing",
                "stage": "轉檔處理",
                "progress_percent": 73,
            }
        )
        self.assertEqual(persisted["progressPercent"], 73)

        legacy = worker_repository.material_job_row_to_dict(
            {
                "id": "job-legacy",
                "status": "processing",
                "stage": "轉檔處理",
            }
        )
        self.assertEqual(legacy["progressPercent"], 66)

        failed = worker_repository.material_job_row_to_dict(
            {
                "id": "job-failed",
                "status": "failed",
                "stage": "處理失敗",
                "progress_percent": 73,
            }
        )
        self.assertEqual(failed["progressPercent"], 73)


if __name__ == "__main__":
    unittest.main()
