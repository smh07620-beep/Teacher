import datetime as dt
import sqlite3
import tempfile
import unittest
from pathlib import Path

from teacher_app.worker import operations
from teacher_app.worker import repository
from teacher_app.worker.protocol_version import (
    MATERIAL_WORKER_PROTOCOL_VERSION,
    MIN_MATERIAL_WORKER_PROTOCOL_VERSION,
    install_capability,
)
from teacher_app.worker.schema import init_schema


ROOT = Path(__file__).parents[1]


class MaterialWorkerProtocolCompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / "worker-protocol.sqlite"
        conn, kind = self.connect()
        try:
            init_schema(conn, kind)
            conn.execute(
                """
                CREATE TABLE material_worker_heartbeats (
                    worker_id TEXT PRIMARY KEY,
                    last_seen TEXT NOT NULL,
                    capabilities TEXT NOT NULL DEFAULT '{}',
                    current_job_id TEXT NOT NULL DEFAULT ''
                )
                """
            )
        finally:
            conn.close()

    def connect(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, "sqlite"

    def seed_job(self, job_id="protocol-job"):
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        return repository.create_material_job(
            {
                "id": job_id,
                "status": "queued",
                "priority": 100,
                "created_at": now,
                "updated_at": now,
                "available_at": now,
                "max_attempts": 3,
                "payload": {"originalName": "lesson.txt", "title": "Lesson"},
                "staging_backend": "r2",
                "staging_key": f"_staging/material-jobs/{job_id}/source.txt",
                "original_name": "lesson.txt",
                "material_id": "material-protocol",
                "source_sha256": "a" * 64,
                "source_bytes": 12,
            },
            connection_factory=self.connect,
        )

    def heartbeat(self, protocol_version):
        repository.upsert_heartbeat(
            "worker-a",
            last_seen=dt.datetime.now(dt.timezone.utc).isoformat(),
            capabilities={
                "protocolVersion": protocol_version,
                "ffmpeg": {"available": True},
                "libreOffice": {"available": True},
            },
            connection_factory=self.connect,
        )

    def test_old_protocol_stays_online_but_cannot_claim_or_consume_attempt(self):
        self.seed_job()
        self.heartbeat(MIN_MATERIAL_WORKER_PROTOCOL_VERSION - 1)
        claimed = repository.claim_next_material_job(
            "worker-a",
            now=dt.datetime.now(dt.timezone.utc).isoformat(),
            connection_factory=self.connect,
        )
        self.assertIsNone(claimed)
        job = repository.get_material_job("protocol-job", connection_factory=self.connect)
        self.assertEqual(job["status"], "queued")
        self.assertEqual(job["attempts"], 0)

        status = operations.status(lambda: {}, connection_factory=self.connect)
        worker = status["workers"][0]
        self.assertFalse(worker["protocolCompatible"])
        self.assertTrue(worker["updateRequired"])
        self.assertEqual(worker["minimumProtocolVersion"], MIN_MATERIAL_WORKER_PROTOCOL_VERSION)

    def test_current_protocol_claims_normally(self):
        self.seed_job()
        self.heartbeat(MATERIAL_WORKER_PROTOCOL_VERSION)
        claimed = repository.claim_next_material_job(
            "worker-a",
            now=dt.datetime.now(dt.timezone.utc).isoformat(),
            connection_factory=self.connect,
        )
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed["status"], "processing")
        self.assertEqual(claimed["attempts"], 1)
        self.assertEqual(claimed["progressPercent"], 30)
        status = operations.status(lambda: {}, connection_factory=self.connect)
        self.assertTrue(status["workers"][0]["protocolCompatible"])

    def test_storage_preflight_failure_stays_online_but_cannot_claim(self):
        self.seed_job("preflight-job")
        repository.upsert_heartbeat(
            "worker-preflight",
            last_seen=dt.datetime.now(dt.timezone.utc).isoformat(),
            capabilities={
                "protocolVersion": MATERIAL_WORKER_PROTOCOL_VERSION,
                "platform": "win32",
                "ffmpeg": {"available": True},
                "libreOffice": {"available": True},
                "storagePreflight": {
                    "ready": False,
                    "backend": "mega",
                    "error": "MEGA login/write probe failed",
                },
            },
            connection_factory=self.connect,
        )
        claimed = repository.claim_next_material_job(
            "worker-preflight",
            now=dt.datetime.now(dt.timezone.utc).isoformat(),
            connection_factory=self.connect,
        )
        self.assertIsNone(claimed)
        job = repository.get_material_job("preflight-job", connection_factory=self.connect)
        self.assertEqual(job["status"], "queued")
        self.assertEqual(job["attempts"], 0)

        worker = operations.status(
            lambda: {}, connection_factory=self.connect
        )["workers"][0]
        self.assertTrue(worker["protocolCompatible"])
        self.assertFalse(worker["storagePreflightReady"])
        self.assertEqual(worker["storagePreflightBackend"], "mega")
        self.assertIn("write probe", worker["storagePreflightError"])
        self.assertFalse(worker["claimReady"])

    def test_status_projects_video_acceleration_and_libreoffice_warm_health(self):
        repository.upsert_heartbeat(
            "worker-phase2",
            last_seen=dt.datetime.now(dt.timezone.utc).isoformat(),
            capabilities={
                "protocolVersion": MATERIAL_WORKER_PROTOCOL_VERSION,
                "platform": "win32",
                "ffmpeg": {"available": True},
                "libreOffice": {"available": True},
                "videoAcceleration": {
                    "enabled": True,
                    "available": True,
                    "encoder": "h264_qsv",
                    "preference": "auto",
                },
                "libreOfficeWarm": {
                    "enabled": True,
                    "running": True,
                    "mode": "warm",
                },
            },
            connection_factory=self.connect,
        )
        worker = operations.status(
            lambda: {}, connection_factory=self.connect
        )["workers"][0]
        self.assertTrue(worker["videoAccelerationEnabled"])
        self.assertTrue(worker["videoAccelerationAvailable"])
        self.assertEqual(worker["videoAccelerationEncoder"], "h264_qsv")
        self.assertTrue(worker["libreOfficeWarmEnabled"])
        self.assertTrue(worker["libreOfficeWarmRunning"])
        self.assertEqual(worker["libreOfficeWarmMode"], "warm")

    def test_capability_installer_is_idempotent(self):
        class Dummy:
            @staticmethod
            def capability():
                return {"platform": "test"}

        install_capability(Dummy)
        install_capability(Dummy)
        payload = Dummy.capability()
        self.assertEqual(payload["protocolVersion"], MATERIAL_WORKER_PROTOCOL_VERSION)
        self.assertEqual(payload["platform"], "test")

    def test_teacher_upload_ui_waits_for_real_completion_and_surfaces_worker_errors(self):
        wizard = ROOT.joinpath("static", "course-wizard-681.js").read_text(encoding="utf-8")
        jobs = ROOT.joinpath("static", "admin-jobs.js").read_text(encoding="utf-8")
        entry = ROOT.joinpath("teacher_app", "worker", "material_worker_entry.py").read_text(encoding="utf-8")
        fallback = ROOT.joinpath("tools", "github_fallback_worker.py").read_text(encoding="utf-8")
        worker = ROOT.joinpath("material_worker.py").read_text(encoding="utf-8")

        for marker in (
            "儲存草稿並離開",
            "等待教材正式完成後才能離開",
            "beforeunload",
            "averageCompletedDurationSeconds",
            "R2 原始檔仍保留",
            "不必重新上傳",
            "canLeaveCourse()",
            "progressPercent",
            "依 Worker 真實回報階段顯示",
        ):
            self.assertIn(marker, wizard)
        for marker in (
            "近期 Worker 錯誤／重試",
            "protocolCompatible===false",
            "原始檔仍保留",
            "不必重新上傳",
            "估計剩餘約",
            "Video ",
            "LO warm",
            "progressPercent",
            "依 Worker 真實回報階段顯示",
        ):
            self.assertIn(marker, jobs)
        for marker in (
            "/api/material-worker/{job_id}/progress",
            '"下載原始檔"',
            '"驗證教材"',
            '"轉檔處理"',
            '"建立預覽"',
            '"正式發布"',
            '"發布確認"',
            '"完成確認"',
        ):
            self.assertIn(marker, worker)
        self.assertIn("install_capability(worker)", entry)
        self.assertIn("install_capability(worker)", fallback)


if __name__ == "__main__":
    unittest.main()
