import json
import unittest
from pathlib import Path

from flask import Flask
from unittest.mock import patch

from teacher_app.common.security import client_ip, login_rate_limit_status, register_production_hardening
from teacher_app.config import configure_app, deployment_config_status, deployment_config_warnings


ROOT = Path(__file__).resolve().parents[1]


class DeploymentConfigTests(unittest.TestCase):
    def production_env(self, **overrides):
        env = {
            "RENDER": "true",
            "DATABASE_URL": "postgresql://user:database-secret@example.invalid/teacher",
            "SECRET_KEY": "s" * 40,
            "ADMIN_KEY": "admin-secret-value",
            "AI_EXTERNAL_PROCESSING_ENABLED": "true",
            "AI_PROVIDER": "groq",
            "GROQ_API_KEY": "groq-secret-value",
            "MATERIAL_BACKGROUND_JOBS": "true",
            "MATERIAL_WORKER_ENABLED": "false",
            "MATERIAL_WORKER_TOKEN": "worker-secret-value",
            "MATERIAL_STORAGE_BACKEND": "mega",
            "MEGA_EMAIL": "teacher@example.invalid",
            "MEGA_PASSWORD": "mega-secret-value",
            "STORAGE_FAILOVER_ON_FULL": "true",
            "STORAGE_FALLBACK_BACKEND": "gdrive",
            "GDRIVE_CLIENT_ID": "gdrive-client-id",
            "GDRIVE_CLIENT_SECRET": "gdrive-secret-value",
            "GDRIVE_REFRESH_TOKEN": "gdrive-refresh-secret-value",
            "GDRIVE_FOLDER_ID": "gdrive-folder",
            "MATERIAL_SHARED_STAGING_BACKEND": "r2",
            "R2_ACCOUNT_ID": "r2-account",
            "R2_ACCESS_KEY_ID": "r2-access-secret-value",
            "R2_SECRET_ACCESS_KEY": "r2-secret-value",
            "R2_BUCKET_NAME": "r2-bucket",
            "WEB_CONCURRENCY": "1",
        }
        env.update(overrides)
        return env

    def test_complete_render_configuration_has_no_warnings(self):
        status = deployment_config_status(self.production_env())
        self.assertTrue(status["ok"])
        self.assertEqual(status["warnings"], [])

    def test_render_blueprint_matches_single_process_deployment_contract(self):
        render = (ROOT / "render.yaml").read_text(encoding="utf-8")
        run_web = (ROOT / "run_web.sh").read_text(encoding="utf-8")

        self.assertIn("runtime: docker", render)
        self.assertIn("numInstances: 1", render)
        self.assertIn("healthCheckPath: /ready", render)
        self.assertEqual(render.count("- type: web"), 1)
        self.assertEqual(render.count("- type: worker"), 1)
        self.assertIn("name: biochemical-training-ai-worker", render)
        self.assertIn("dockerCommand: python -u ai_question_worker.py", render)
        self.assertIn("plan: 0.5c-512mb", render)
        self.assertIn("--workers ${WEB_CONCURRENCY:-1}", run_web)
        self.assertIn("pgy_app:app", run_web)

        for key in (
            "DATABASE_URL",
            "ADMIN_KEY",
            "SECRET_KEY",
            "GROQ_API_KEY",
            "MATERIAL_WORKER_TOKEN",
            "MEGA_EMAIL",
            "MEGA_PASSWORD",
            "GDRIVE_CLIENT_ID",
            "GDRIVE_CLIENT_SECRET",
            "GDRIVE_REFRESH_TOKEN",
            "GDRIVE_FOLDER_ID",
            "R2_ACCOUNT_ID",
            "R2_ACCESS_KEY_ID",
            "R2_SECRET_ACCESS_KEY",
            "R2_BUCKET_NAME",
        ):
            self.assertRegex(render, rf"- key: {key}\s+sync: false")

    def test_missing_core_and_enabled_service_settings_are_actionable(self):
        env = self.production_env(
            DATABASE_URL="",
            SECRET_KEY="short",
            ADMIN_KEY="",
            GROQ_API_KEY="",
            MATERIAL_WORKER_TOKEN="",
            MEGA_PASSWORD="",
            GDRIVE_REFRESH_TOKEN="",
            R2_SECRET_ACCESS_KEY="",
            WEB_CONCURRENCY="2",
        )
        warnings = deployment_config_warnings(env)
        codes = {item["code"] for item in warnings}
        self.assertTrue(
            {
                "database_url_missing",
                "secret_key_invalid",
                "admin_key_missing",
                "groq_api_key_missing",
                "material_worker_token_missing",
                "mega_credentials_incomplete",
                "gdrive_credentials_incomplete",
                "r2_credentials_incomplete",
                "login_rate_limit_process_local",
            }.issubset(codes)
        )
        self.assertFalse(deployment_config_status(env)["ok"])

    def test_warnings_never_include_secret_values(self):
        env = self.production_env(
            GDRIVE_REFRESH_TOKEN="",
            R2_SECRET_ACCESS_KEY="",
            MEGA_PASSWORD="",
        )
        serialized = json.dumps(deployment_config_warnings(env), ensure_ascii=False)
        for secret in (
            env["DATABASE_URL"],
            env["SECRET_KEY"],
            env["ADMIN_KEY"],
            env["GROQ_API_KEY"],
            env["MATERIAL_WORKER_TOKEN"],
            env["GDRIVE_CLIENT_SECRET"],
            env["R2_ACCESS_KEY_ID"],
        ):
            self.assertNotIn(secret, serialized)
        self.assertIn("GDRIVE_REFRESH_TOKEN", serialized)
        self.assertIn("R2_SECRET_ACCESS_KEY", serialized)
        self.assertIn("MEGA_PASSWORD", serialized)

    def test_local_development_keeps_sqlite_and_dev_secret_supported(self):
        status = deployment_config_status(
            {
                "MATERIAL_STORAGE_BACKEND": "local",
                "MATERIAL_SHARED_STAGING_BACKEND": "local",
                "WEB_CONCURRENCY": "1",
            }
        )
        self.assertTrue(status["ok"])
        self.assertEqual(status["warnings"], [])

    def test_process_local_rate_limit_explicitly_reports_supported_topology(self):
        with patch.dict("os.environ", {"WEB_CONCURRENCY": "1"}, clear=False):
            status = login_rate_limit_status()
        self.assertEqual(status["backend"], "process-local")
        self.assertFalse(status["shared"])
        self.assertTrue(status["topologySupported"])
        self.assertIn("single web process", status["supportedTopology"])

        with patch.dict("os.environ", {"WEB_CONCURRENCY": "3"}, clear=False):
            status = login_rate_limit_status()
        self.assertFalse(status["topologySupported"])

    def test_login_rate_limit_ip_does_not_trust_client_forwarded_header_off_render(self):
        app = Flask("rate-limit-client-ip-local")
        with patch.dict("os.environ", {"RENDER": "false"}, clear=False), app.test_request_context(
            "/api/auth/login",
            method="POST",
            headers={"X-Forwarded-For": "203.0.113.55"},
            environ_base={"REMOTE_ADDR": "198.51.100.25"},
        ):
            self.assertEqual(client_ip(), "198.51.100.25")

    def test_render_rate_limit_uses_proxy_observed_rightmost_forwarded_address(self):
        app = Flask("rate-limit-client-ip-render")
        with patch.dict("os.environ", {"RENDER": "true"}, clear=False), app.test_request_context(
            "/api/auth/login",
            method="POST",
            headers={"X-Forwarded-For": "203.0.113.99, 198.51.100.44"},
            environ_base={"REMOTE_ADDR": "10.0.0.5"},
        ):
            self.assertEqual(client_ip(), "198.51.100.44")

    def test_security_status_uses_canonical_multi_role_rbac(self):
        app = Flask("security-status-multirole")
        app.config.update(TESTING=True, SECRET_KEY="security-status-test")
        actor = {
            "username": "multi-admin",
            "role": "clinical_teacher",
            "roles": ["clinical_teacher", "system_admin"],
        }
        register_production_hardening(app, current_user=lambda: actor, login_failures={})
        response = app.test_client().get("/api/security/status")
        self.assertEqual(response.status_code, 200)
        self.assertIn("loginRateLimit", response.get_json())

        actor.clear()
        actor.update({"username": "student", "role": "student", "roles": ["student"]})
        denied = app.test_client().get("/api/security/status")
        self.assertEqual(denied.status_code, 403)

    def test_configure_app_exposes_and_logs_startup_validation_without_values(self):
        env = self.production_env(DATABASE_URL="", SECRET_KEY="short", ADMIN_KEY="")
        app = Flask("deployment-validation-test")
        with patch.dict("os.environ", env, clear=True), patch.object(
            app.logger,
            "error",
        ) as error_log, patch.object(app.logger, "warning") as warning_log:
            configure_app(app)

        status = app.config["DEPLOYMENT_CONFIGURATION"]
        codes = {item["code"] for item in status["warnings"]}
        self.assertIn("database_url_missing", codes)
        self.assertIn("secret_key_invalid", codes)
        self.assertIn("admin_key_missing", codes)
        self.assertTrue(error_log.called)
        self.assertTrue(warning_log.called)
        serialized_calls = repr(error_log.call_args_list + warning_log.call_args_list)
        self.assertNotIn("database-secret", serialized_calls)
        self.assertNotIn("admin-secret-value", serialized_calls)

    def test_short_production_secret_fails_startup_without_echoing_secret(self):
        app = Flask("deployment-short-secret-startup")
        short_secret = "short-production-secret"
        with patch.dict(
            "os.environ",
            {
                "PRODUCTION_REQUIRE_SECRET": "true",
                "SECRET_KEY": short_secret,
            },
            clear=True,
        ):
            with self.assertRaises(RuntimeError) as raised:
                register_production_hardening(app, current_user=lambda: None, login_failures={})

        message = str(raised.exception)
        self.assertEqual(
            message,
            "Production requires SECRET_KEY with at least 32 characters.",
        )
        self.assertNotIn(short_secret, message)


if __name__ == "__main__":
    unittest.main()
