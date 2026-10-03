"""Regressions for stable Worker identity, observability, and fail-closed scope."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask, g, jsonify

from teacher_app.common import scope_filter
from teacher_app.worker import operations


ROOT = Path(__file__).parents[1]


class StableWorkerIdentityTests(unittest.TestCase):
    def test_worker_identity_is_persisted_outside_git_and_respects_explicit_env(self):
        gitignore = ROOT.joinpath(".gitignore").read_text(encoding="utf-8")
        installer = ROOT.joinpath("install_material_worker_task.ps1").read_text(encoding="utf-8")
        supervisor = ROOT.joinpath("run_material_worker_autostart.ps1").read_text(encoding="utf-8")

        self.assertIn(".worker-id", gitignore)
        for marker in (
            "function Ensure-StableWorkerId",
            'Join-Path $root ".worker-id"',
            "[Guid]::NewGuid()",
        ):
            self.assertIn(marker, installer)
            self.assertIn(marker, supervisor)
        self.assertIn("MATERIAL_WORKER_ID", installer)
        self.assertIn('[Environment]::SetEnvironmentVariable("MATERIAL_WORKER_ID", $workerId, "Process")', supervisor)
        self.assertIn("if ([string]$env:MATERIAL_WORKER_ID)", supervisor)

        worker = ROOT.joinpath("material_worker.py").read_text(encoding="utf-8")
        self.assertIn('WORKER_ID=os.environ.get("MATERIAL_WORKER_ID", "").strip() or f"{_FALLBACK_MACHINE}-TeacherWorker"', worker)
        self.assertNotIn('f"{socket.gethostname()}:{os.getpid()}"', worker)
        self.assertIn('RUNTIME_LOCK_PATH=ROOT/".worker-runtime.lock"', worker)
        self.assertIn("def acquire_worker_runtime_lock()", worker)
        self.assertIn("DUPLICATE_RUNTIME=76", worker)
        self.assertIn("if ($workerExit -eq 76)", supervisor)
        self.assertIn(".worker-runtime.lock", gitignore)


class WorkerStatusObservabilityTests(unittest.TestCase):
    def _status(self):
        return operations.status(lambda: {"backend": "r2", "available": True, "shared": True})

    def test_heartbeat_repository_failure_is_not_reported_as_zero_workers(self):
        with (
            patch.object(operations.repository, "queue_aggregates", return_value={}),
            patch.object(operations.repository, "list_material_jobs", return_value=[]),
            patch.object(operations.repository, "list_heartbeats", side_effect=RuntimeError("postgres://secret@example")),
            patch.object(operations.r2_budget, "status", return_value={}),
            patch.object(operations.LOGGER, "exception") as log_exception,
        ):
            result = self._status()

        self.assertFalse(result["workerStatusAvailable"])
        self.assertEqual(result["workers"], [])
        self.assertTrue(result["workerStatusError"])
        self.assertNotIn("secret", result["workerStatusError"].lower())
        log_exception.assert_called_once()

    def test_successful_empty_heartbeat_query_is_distinguishable(self):
        with (
            patch.object(operations.repository, "queue_aggregates", return_value={}),
            patch.object(operations.repository, "list_material_jobs", return_value=[]),
            patch.object(operations.repository, "list_heartbeats", return_value=[]),
            patch.object(operations.r2_budget, "status", return_value={}),
        ):
            result = self._status()
        self.assertTrue(result["workerStatusAvailable"])
        self.assertEqual(result["workerStatusError"], "")
        self.assertEqual(result["workers"], [])

    def test_status_api_and_frontends_expose_unavailable_state(self):
        routes = ROOT.joinpath("teacher_app", "materials", "job_routes.py").read_text(encoding="utf-8")
        worker_ui = ROOT.joinpath("static", "worker-status-70.js").read_text(encoding="utf-8")
        jobs_ui = ROOT.joinpath("static", "admin-jobs.js").read_text(encoding="utf-8")
        self.assertIn('"workerStatusAvailable"', routes)
        self.assertIn('"workerStatusError"', routes)
        for source in (worker_ui, jobs_ui):
            self.assertIn("workerStatusAvailable", source)
            self.assertIn("workerStatusError", source)
            self.assertIn("狀態讀取異常", source)
        self.assertIn("此訊息不代表 Worker 已離線", worker_ui)


class WorkerFailureObservabilityTests(unittest.TestCase):
    def test_staging_probe_error_is_logged_and_does_not_mark_job_missing(self):
        job = {
            "id": "job-probe-error",
            "workerId": "worker-a",
            "updatedAt": "2026-09-18T09:00:00+00:00",
            "stagingBackend": "r2",
        }
        with (
            patch.object(operations.repository, "list_stale_processing_jobs", return_value=[job]),
            patch.object(operations.repository, "cas_material_job") as cas_job,
            patch.object(operations.LOGGER, "warning") as log_warning,
        ):
            result = operations.recover_stale_processing_jobs(
                lambda _job: (_ for _ in ()).throw(RuntimeError("provider unavailable")),
                stale_seconds=300,
                now=__import__("datetime").datetime(
                    2026, 9, 18, 11, 0, tzinfo=__import__("datetime").timezone.utc
                ),
            )

        self.assertEqual(result.get("stagingProbeErrors"), 1)
        cas_job.assert_not_called()
        log_warning.assert_called_once()

    def test_cleanup_failure_is_logged_and_remains_pending(self):
        job = {
            "id": "job-cleanup-error",
            "status": "failed",
            "updatedAt": "2026-09-18T09:00:00+00:00",
            "cleanupPending": True,
            "stagingBackend": "r2",
        }
        with (
            patch.object(operations.repository, "list_cleanup_candidates", return_value=[job]),
            patch.object(operations.repository, "update_material_job") as update_job,
            patch.object(operations.LOGGER, "warning") as log_warning,
        ):
            operations.cleanup_staging(
                lambda _job: (_ for _ in ()).throw(RuntimeError("provider unavailable"))
            )

        log_warning.assert_called_once()
        self.assertTrue(update_job.call_args.kwargs["fields"]["cleanup_pending"])

    def test_worker_and_progress_fallbacks_have_non_secret_observability(self):
        root = ROOT
        worker = root.joinpath("material_worker.py").read_text(encoding="utf-8")
        routes = root.joinpath("teacher_app", "worker", "routes.py").read_text(encoding="utf-8")
        metadata = root.joinpath("teacher_app", "worker", "media_metadata.py").read_text(encoding="utf-8")
        jobs = root.joinpath("teacher_app", "materials", "job_routes.py").read_text(encoding="utf-8")
        for marker, source in (
            ("material text index build failed", worker),
            ("worker upload multipart abort cleanup failed", routes),
            ("worker upload object delete cleanup failed", routes),
            ("worker media metadata mirror failed", routes),
            ("media processing metadata sync skipped", metadata),
            ("material upload progress read failed", jobs),
        ):
            self.assertIn(marker, source)
        for source in (worker, routes, metadata, jobs):
            self.assertIn("error_type=%s", source)


class ScopeFailClosedTests(unittest.TestCase):
    def _app(self, user):
        app = Flask(__name__)
        app.config["TESTING"] = True

        @app.before_request
        def bind_user():
            g.teacher_user = dict(user)

        @app.put("/probe/material/<material_id>")
        def probe(material_id):
            del material_id
            denied = scope_filter.require_permission(app, "material.manage")
            if denied:
                return denied
            return jsonify({"ok": True})

        return app

    def test_group_scoped_actor_fails_closed_when_target_lookup_errors(self):
        app = self._app({"role": "group_leader", "roles": ["group_leader"], "preferredGroup": "grpBio"})
        with (
            patch.object(
                scope_filter.material_repository,
                "get_material",
                side_effect=RuntimeError("postgres://super-secret@example"),
            ),
            patch.object(scope_filter.LOGGER, "warning") as warning,
        ):
            response = app.test_client().put("/probe/material/mat-1", json={})
        self.assertEqual(response.status_code, 503)
        self.assertTrue(response.get_json()["scopeResolutionFailed"])
        self.assertGreaterEqual(warning.call_count, 2)
        rendered = "\n".join(str(call) for call in warning.call_args_list)
        self.assertIn("scope resource lookup failed", rendered)
        self.assertIn("scope authorization resolution denied", rendered)
        self.assertIn("RuntimeError", rendered)
        self.assertNotIn("super-secret", rendered)

    def test_group_scoped_actor_fails_closed_when_target_group_is_missing(self):
        app = self._app({"role": "group_leader", "roles": ["group_leader"], "preferredGroup": "grpBio"})
        with (
            patch.object(scope_filter.material_repository, "get_material", return_value={"id": "mat-1"}),
            patch.object(scope_filter.LOGGER, "warning") as warning,
        ):
            response = app.test_client().put("/probe/material/mat-1", json={})
        self.assertEqual(response.status_code, 503)
        self.assertTrue(
            any(
                "scope authorization resolution denied" in str(call)
                for call in warning.call_args_list
            )
        )

    def test_group_scope_still_allows_own_group_and_denies_other_group(self):
        app = self._app({"role": "group_leader", "roles": ["group_leader"], "preferredGroup": "grpBio"})
        with patch.object(scope_filter.material_repository, "get_material", return_value={"id": "mat-1", "group": "grpBio"}):
            own = app.test_client().put("/probe/material/mat-1", json={})
        with patch.object(scope_filter.material_repository, "get_material", return_value={"id": "mat-2", "group": "grpHema"}):
            other = app.test_client().put("/probe/material/mat-2", json={})
        self.assertEqual(own.status_code, 200)
        self.assertEqual(other.status_code, 403)

    def test_scope_helper_repository_errors_are_logged_without_exception_message(self):
        app = Flask(__name__)
        app.config["TESTING"] = True
        with app.test_request_context("/probe"):
            with (
                patch.object(
                    scope_filter.assessment_repository,
                    "get_question",
                    side_effect=RuntimeError("credential=do-not-log"),
                ),
                patch.object(scope_filter.LOGGER, "warning") as warning,
            ):
                self.assertEqual(scope_filter.question_group(app, "question-1"), "")

        rendered = "\n".join(str(call) for call in warning.call_args_list)
        self.assertIn("scope resource lookup failed", rendered)
        self.assertIn("question-1", rendered)
        self.assertIn("RuntimeError", rendered)
        self.assertNotIn("do-not-log", rendered)


    def test_organization_wide_admin_keeps_cross_group_permission_on_lookup_failure(self):
        app = self._app({"role": "education_admin", "roles": ["education_admin"], "preferredGroup": "grpBio"})
        with patch.object(scope_filter.material_repository, "get_material", side_effect=RuntimeError("database unavailable")):
            response = app.test_client().put("/probe/material/mat-1", json={})
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
