import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from teacher_app.assessments import ai_job_repository, ai_job_schema, ai_jobs


ROOT = Path(__file__).resolve().parents[1]


class AiQuestionJobRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "ai-jobs.sqlite"

        def connect():
            conn = sqlite3.connect(str(self.path), timeout=30)
            conn.row_factory = sqlite3.Row
            conn.isolation_level = None
            return conn, "sqlite"

        self.connect = connect
        conn, kind = connect()
        try:
            ai_job_schema.init_schema(conn, kind)
        finally:
            conn.close()
        self.db_patch = patch("teacher_app.common.db.get_connection", side_effect=connect)
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)

    def create_job(self, job_id="job-1"):
        return ai_job_repository.create_job({
            "id": job_id,
            "quiz_category_id": "cat-1",
            "group_key": "grpBio",
            "training_area": "internal",
            "actor_username": "teacher",
            "request": {"quizCategoryId": "cat-1", "materialIds": ["mat-1"]},
        })

    def test_atomic_claim_allows_exactly_one_process_local_runner(self):
        self.create_job()
        with ThreadPoolExecutor(max_workers=2) as pool:
            claims = list(pool.map(
                lambda token: ai_job_repository.claim("job-1", token),
                ("claim-a", "claim-b"),
            ))
        winners = [job for job in claims if job is not None]
        self.assertEqual(len(winners), 1)
        persisted = ai_job_repository.get_job("job-1")
        self.assertEqual(persisted["status"], "processing")
        self.assertEqual(persisted["attempts"], 1)

    def test_progress_result_and_failure_are_persistent_and_claim_bound(self):
        self.create_job("complete")
        claimed = ai_job_repository.claim("complete", "token")
        self.assertIsNotNone(claimed)
        self.assertFalse(ai_job_repository.set_progress("complete", "wrong", 50, "wrong", "wrong"))
        self.assertTrue(ai_job_repository.set_progress("complete", "token", 55, "分析教材", "正在分析"))
        self.assertTrue(ai_job_repository.complete("complete", "token", {"questions": [{"question": "AI"}]}))
        completed = ai_job_repository.get_job("complete")
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["progressPercent"], 100)
        self.assertEqual(completed["result"]["questions"][0]["question"], "AI")

        self.create_job("failed")
        self.assertIsNotNone(ai_job_repository.claim("failed", "failure-token"))
        self.assertTrue(ai_job_repository.fail("failed", "failure-token", "provider failed"))
        failed = ai_job_repository.get_job("failed")
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["error"], "provider failed")

    def test_ai_queue_is_assessment_owned_and_does_not_reuse_material_jobs(self):
        for relative in (
            "teacher_app/assessments/ai_job_schema.py",
            "teacher_app/assessments/ai_job_repository.py",
            "teacher_app/assessments/ai_jobs.py",
        ):
            source = ROOT.joinpath(relative).read_text(encoding="utf-8")
            self.assertNotIn("material_jobs", source, relative)
        self.assertIn("ai_question_jobs", ROOT.joinpath(
            "teacher_app/assessments/ai_job_schema.py"
        ).read_text(encoding="utf-8"))

    def test_dedicated_worker_owns_execution_not_flask_routes(self):
        jobs_source = ROOT.joinpath("teacher_app/assessments/ai_jobs.py").read_text(encoding="utf-8")
        routes_source = ROOT.joinpath("teacher_app/assessments/runtime_question_routes.py").read_text(encoding="utf-8")
        worker_source = ROOT.joinpath("ai_question_worker.py").read_text(encoding="utf-8")
        self.assertNotIn("ThreadPoolExecutor", jobs_source)
        self.assertNotIn("AiQuestionJobProcessor(", routes_source)
        self.assertNotIn("run_job(", routes_source)
        self.assertIn("AiQuestionJobProcessor", worker_source)
        self.assertIn("run_next_queued", worker_source)

    def test_processor_claims_and_completes_one_queued_job(self):
        self.create_job("worker-job")
        processor = ai_jobs.AiQuestionJobProcessor(object())
        with patch.object(
            ai_jobs,
            "run_generation_sync",
            return_value={"questions": [{"question": "worker result"}]},
        ) as generate:
            self.assertTrue(processor.run_next_queued())
        generate.assert_called_once()
        persisted = ai_job_repository.get_job("worker-job")
        self.assertEqual(persisted["status"], "completed")
        self.assertEqual(persisted["result"]["questions"][0]["question"], "worker result")

    def test_request_snapshot_deidentifies_focus_before_persistence(self):
        runtime = type("Runtime", (), {"max_materials": 4, "max_questions": 15})()
        with patch.object(
            ai_jobs.repository,
            "get_category_full",
            return_value={"id": "cat-1", "group": "grpBio", "area": "internal"},
        ), patch.object(
            ai_jobs.material_repository,
            "get_material",
            return_value={"id": "mat-1", "active": True, "group": "grpBio", "area": "internal"},
        ):
            values = ai_jobs.prepare_request(
                {
                    "quizCategoryId": "cat-1",
                    "materialIds": ["mat-1"],
                    "focus": "姓名：王小明 病歷號：ABC12345",
                },
                runtime,
                {"username": "teacher"},
            )
        self.assertNotIn("王小明", values["request"]["focus"])
        self.assertNotIn("ABC12345", values["request"]["focus"])
        self.assertIn("[已遮罩]", values["request"]["focus"])


if __name__ == "__main__":
    unittest.main()
