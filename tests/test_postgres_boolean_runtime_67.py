import contextlib
import re
import unittest
from pathlib import Path
from unittest.mock import patch

import app as appmod
import pgy_app


BOOLEAN_INTEGER_COMPARISON = re.compile(
    r"\b(cleanup_pending|cancel_requested|is_staging|active|completed)\s*(?:=|<>)\s*[01]\b",
    re.IGNORECASE,
)


class Result:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def fetchall(self):
        return list(self.rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None


class RecordingConnection:
    def __init__(self, terminal_jobs=()):
        self.calls = []
        self.terminal_jobs = list(terminal_jobs)

    def execute(self, sql, params=()):
        normalized = " ".join(str(sql).split())
        self.calls.append((normalized, tuple(params or ())))
        lowered = normalized.lower()
        if "select id,staging_path,staging_backend" in lowered:
            return Result(self.terminal_jobs)
        if "count(*) as count from material_jobs where cleanup_pending" in lowered:
            return Result([{"count": 0}])
        if "sum(multipart_parts)" in lowered:
            return Result([{"count": 0, "operations": 0}])
        return Result()

    def transaction(self):
        return contextlib.nullcontext()

    def close(self):
        pass


class ClaimConnection(RecordingConnection):
    def __init__(self):
        super().__init__()
        self.job = {
            "id": "job-1",
            "status": "queued",
            "attempts": 0,
            "max_attempts": 3,
            "payload": {},
            "result": {},
            "cancel_requested": False,
        }

    def execute(self, sql, params=()):
        result = super().execute(sql, params)
        normalized = self.calls[-1][0].lower()
        if normalized.startswith("select * from material_jobs where status in"):
            return Result([dict(self.job)])
        if normalized.startswith("select * from material_jobs where id="):
            return Result([{**self.job, "status": "processing", "attempts": 1}])
        return result


class PostgreSQLBooleanRuntime67Tests(unittest.TestCase):
    def sql(self, connection):
        return [query for query, _params in connection.calls]

    def assert_no_boolean_integer_comparisons(self, connection):
        offenders = [query for query in self.sql(connection) if BOOLEAN_INTEGER_COMPARISON.search(query)]
        self.assertEqual(offenders, [])

    def test_r2_budget_status_uses_postgres_true(self):
        connection = RecordingConnection()
        with patch.object(appmod, "_db_conn", return_value=(connection, "postgres")):
            status = appmod.r2_budget_status()
        self.assertEqual(status["cleanupPending"], 0)
        self.assertTrue(any("cleanup_pending=TRUE" in query for query in self.sql(connection)))
        self.assertFalse(any("cleanup_pending=1" in query for query in self.sql(connection)))
        self.assert_no_boolean_integer_comparisons(connection)

    def test_r2_budget_status_keeps_sqlite_integer_literal(self):
        connection = RecordingConnection()
        with patch.object(appmod, "_db_conn", return_value=(connection, "sqlite")):
            status = appmod.r2_budget_status()
        self.assertEqual(status["cleanupPending"], 0)
        self.assertTrue(any("cleanup_pending=1" in query for query in self.sql(connection)))

    def test_postgres_claim_and_staging_queries_use_boolean_literals(self):
        connection = ClaimConnection()
        with patch.object(appmod, "_db_conn", return_value=(connection, "postgres")):
            job = appmod.claim_next_material_job("worker-1")
            appmod._r2_staging_totals(connection)
        self.assertEqual(job["id"], "job-1")
        self.assertTrue(any("cancel_requested=FALSE" in query for query in self.sql(connection)))
        self.assertTrue(any("is_staging=TRUE" in query for query in self.sql(connection)))
        self.assert_no_boolean_integer_comparisons(connection)

    def test_cleanup_uses_python_bool_parameters_for_postgres(self):
        terminal = [{
            "id": "job-1",
            "status": "failed",
            "updated_at": "2000-01-01T00:00:00+00:00",
            "staging_path": "",
            "staging_backend": "r2",
            "staging_key": "_staging/job-1",
            "cleanup_pending": True,
        }]
        failed = RecordingConnection(terminal)
        with patch.object(appmod, "_db_conn", return_value=(failed, "postgres")), patch.object(
            appmod, "delete_material_job_staging", side_effect=RuntimeError("temporary")
        ):
            appmod.cleanup_material_job_staging()
        update_params = [params for query, params in failed.calls if query.startswith("UPDATE material_jobs SET cleanup_pending")]
        self.assertEqual(len(update_params), 1)
        self.assertIs(update_params[0][0], True)

        succeeded = RecordingConnection(terminal)
        with patch.object(appmod, "_db_conn", return_value=(succeeded, "postgres")), patch.object(
            appmod, "delete_material_job_staging", return_value=None
        ):
            appmod.cleanup_material_job_staging()
        update_params = [params for query, params in succeeded.calls if query.startswith("UPDATE material_jobs SET staging_path")]
        self.assertEqual(len(update_params), 1)
        self.assertIs(update_params[0][0], False)

    def test_postgres_material_active_queries_do_not_use_integer_literals(self):
        connection = RecordingConnection()
        with patch.object(appmod, "_db_conn", return_value=(connection, "postgres")):
            appmod.list_uploaded_materials(False)
            appmod.list_courses(include_inactive=False)
            appmod.list_quiz_categories(include_inactive=False)
            appmod.list_quiz_questions("quiz-1", include_inactive=False)
            appmod.quiz_question_counts(["quiz-1"], include_inactive=False)
        active_queries = [query for query in self.sql(connection) if "active" in query.lower()]
        self.assertTrue(active_queries)
        self.assertTrue(all("TRUE" in query for query in active_queries))
        self.assert_no_boolean_integer_comparisons(connection)

    def test_learning_progress_postgres_sql_uses_boolean_expression(self):
        source = Path("smart_learning_67.py").read_text(encoding="utf-8")
        postgres_sql = source.split('if kind == "postgres":', 1)[1].split("else:", 1)[0]
        self.assertIn("learning_progress.completed OR EXCLUDED.completed", postgres_sql)
        self.assertIn("CASE WHEN EXCLUDED.completed THEN", postgres_sql)
        self.assertIsNone(BOOLEAN_INTEGER_COMPARISON.search(postgres_sql))

    def test_material_jobs_api_postgres_recorder_path_succeeds(self):
        connection = RecordingConnection()
        with patch.object(appmod, "_db_conn", return_value=(connection, "postgres")), patch.object(
            appmod, "require_admin", return_value=None
        ):
            response = pgy_app.app.test_client().get("/api/material-jobs")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertIn("r2Budget", response.get_json())
        self.assertTrue(any("cleanup_pending=TRUE" in query for query in self.sql(connection)))
        self.assert_no_boolean_integer_comparisons(connection)


if __name__ == "__main__":
    unittest.main()
