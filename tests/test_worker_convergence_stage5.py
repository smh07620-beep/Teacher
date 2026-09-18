"""Ownership guards for bounded Stage 5 worker convergence."""
import unittest
from pathlib import Path
from unittest.mock import patch

from teacher_app.worker import protocol


ROOT = Path(__file__).parents[1]


class WorkerConvergenceStage5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = ROOT.joinpath("free_worker_67.py").read_text(encoding="utf-8")
        cls.local_worker = ROOT.joinpath("material_worker.py").read_text(encoding="utf-8")
        cls.protocol = ROOT.joinpath(
            "teacher_app", "worker", "protocol.py"
        ).read_text(encoding="utf-8")
        cls.repository = ROOT.joinpath(
            "teacher_app", "worker", "repository.py"
        ).read_text(encoding="utf-8")

    def test_heartbeat_sql_is_owned_by_canonical_repository(self):
        self.assertIn("def upsert_heartbeat(", self.repository)
        self.assertIn("INSERT INTO material_worker_heartbeats", self.repository)
        self.assertNotIn("INSERT INTO material_worker_heartbeats", self.adapter)
        self.assertNotIn("ON CONFLICT(worker_id)", self.adapter)

    def test_worker_identity_metadata_and_heartbeat_are_canonical(self):
        for marker in (
            "def normalize_worker_id(",
            "def sanitize_metadata(",
            "def heartbeat_capabilities(",
            "def record_heartbeat(",
        ):
            self.assertIn(marker, self.protocol)
        self.assertNotIn("from flask", self.protocol)
        self.assertNotIn("import app", self.protocol)
        self.assertNotIn("base.", self.protocol)
        self.assertIn("worker_protocol.record_heartbeat", self.adapter)

    def test_canonical_worker_domain_does_not_create_second_executor(self):
        combined = self.protocol + self.repository
        for marker in (
            "def main(",
            "def process_one(",
            "def publish_to_storage(",
            "import requests",
            "import subprocess",
        ):
            self.assertNotIn(marker, combined)
        self.assertIn("def main(", self.local_worker)
        self.assertIn("def process_one(", self.local_worker)
        self.assertIn("def publish_to_storage(", self.local_worker)

    def test_remaining_worker_debt_stays_explicit_and_bounded(self):
        self.assertIn("material_upload_sessions", self.adapter)
        self.assertIn("def terminal(", self.adapter)
        self.assertIn("base.claim_next_material_job", self.adapter)
        self.assertIn("base.commit_material_job_result", self.adapter)

    def test_phase4_groundwork_owns_queue_and_upload_session_persistence(self):
        for marker in (
            "def material_job_row_to_dict(",
            "def create_material_job(",
            "def get_material_job(",
            "def list_material_jobs(",
            "def cas_material_job(",
            "def transition_owned_material_job(",
            "def claim_next_material_job(",
            "def list_stale_processing_jobs(",
            "def list_cleanup_candidates(",
            "def queue_aggregates(",
            "def count_cleanup_pending_jobs(",
            "def list_heartbeats(",
            "def create_upload_session(",
            "def get_upload_session(",
            "def cas_upload_session_status(",
            "def upload_session_status_counts(",
            "def finalize_upload_session_with_job(",
        ):
            self.assertIn(marker, self.repository)
        self.assertNotIn("CREATE TABLE", self.repository)
        self.assertNotIn("ALTER TABLE", self.repository)

    def test_phase4_protocol_rules_are_pure_and_canonical(self):
        for marker in (
            "def bearer_token_matches(",
            "def retry_plan(",
            "def validate_multipart_parts(",
        ):
            self.assertIn(marker, self.protocol)
        combined = self.protocol + self.repository
        for forbidden in ("from flask", "import requests", "import subprocess", "r2_client"):
            self.assertNotIn(forbidden, combined)

    def test_protocol_preserves_metadata_and_job_touch_contract(self):
        touched = []
        with patch.object(protocol.repository, "upsert_heartbeat") as upsert:
            stamp = protocol.record_heartbeat(
                "worker-1",
                capabilities={"ffmpeg": {"available": True}},
                current_job_id="job-1",
                metadata={
                    "workerVersion": "6.8.1!",
                    "workerSha": "ABCDEF1",
                    "workerBranch": "feature/test branch",
                    "updateAvailable": True,
                    "lastUpdateCheckAt": "2026-09-18T10:00:00+00:00",
                    "secret": "must-not-pass",
                },
                stamp="2026-09-18T11:00:00+00:00",
                touch_job=lambda job_id, seen: touched.append((job_id, seen)),
            )
        self.assertEqual(stamp, "2026-09-18T11:00:00+00:00")
        payload = upsert.call_args.kwargs["capabilities"]
        self.assertEqual(payload["workerVersion"], "6.8.1")
        self.assertEqual(payload["workerSha"], "abcdef1")
        self.assertEqual(payload["workerBranch"], "feature/testbranch")
        self.assertTrue(payload["updateAvailable"])
        self.assertNotIn("secret", payload)
        self.assertEqual(touched, [("job-1", stamp)])


if __name__ == "__main__":
    unittest.main()
