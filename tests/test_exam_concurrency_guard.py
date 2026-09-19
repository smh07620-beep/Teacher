import threading
import unittest
from pathlib import Path

from teacher_app.exams import repository as repo


ROOT = Path(__file__).parents[1]


class ExamFrontendConcurrencyContractTests(unittest.TestCase):
    def test_exam_attempt_loader_has_inflight_deduplication(self):
        source = ROOT.joinpath("static", "system-exam.js").read_text(encoding="utf-8")
        self.assertIn("secureAttemptLoadMap", source)
        self.assertIn("secureAttemptLoadMap[catId]", source)
        self.assertIn("delete secureAttemptLoadMap[catId]", source)


class _SQLiteBase:
    def __init__(self, path):
        self.path = path

    def _db_conn(self):
        import sqlite3
        conn = sqlite3.connect(str(self.path), timeout=5)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, "sqlite"


class ExamSubmitConcurrencyTests(unittest.TestCase):
    def test_only_one_concurrent_submit_can_mark_attempt(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            base = _SQLiteBase(Path(tmp) / "exam.sqlite3")
            repo.init_schema(base)
            with repo.transaction(base) as (conn, kind):
                repo.create_attempt(conn, kind, {
                    "id": "attempt-1",
                    "username": "student",
                    "emp_id": "E1",
                    "quiz_category_id": "quiz-1",
                    "quiz_title": "Quiz",
                    "group_key": "grpBio",
                    "training_area": "internal",
                    "course_id": "",
                    "passing_score": 80,
                    "publication_id": "",
                    "publication_hash": "",
                    "questions_json": "[]",
                    "status": "started",
                    "record_id": "",
                    "started_at": "2026-09-17T00:00:00+00:00",
                    "submitted_at": "",
                })

            barrier = threading.Barrier(2)
            results = []
            lock = threading.Lock()

            def submit(record_id):
                try:
                    barrier.wait(timeout=2)
                    with repo.transaction(base) as (conn, kind):
                        repo.mark_submitted(conn, kind, "attempt-1", record_id, "now")
                    outcome = "ok"
                except repo.AttemptConflict:
                    outcome = "conflict"
                with lock:
                    results.append(outcome)

            threads = [
                threading.Thread(target=submit, args=("record-a",)),
                threading.Thread(target=submit, args=("record-b",)),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)

            self.assertEqual(sorted(results), ["conflict", "ok"])


if __name__ == "__main__":
    unittest.main()
