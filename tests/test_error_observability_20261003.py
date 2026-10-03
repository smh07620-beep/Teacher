import unittest
from pathlib import Path

from teacher_app.worker import error_observability


ROOT = Path(__file__).parents[1]


class ErrorObservability20261003Tests(unittest.TestCase):
    def test_external_io_fallbacks_emit_safe_operational_logs(self):
        r2 = ROOT.joinpath("teacher_app", "storage", "r2_budget.py").read_text(encoding="utf-8")
        reminders = ROOT.joinpath("teacher_app", "notifications", "reminders.py").read_text(encoding="utf-8")
        pgy = ROOT.joinpath("teacher_app", "pgy", "assessment_routes.py").read_text(encoding="utf-8")
        materials = ROOT.joinpath("teacher_app", "materials", "service.py").read_text(encoding="utf-8")
        scope_filter = ROOT.joinpath("teacher_app", "common", "scope_filter.py").read_text(encoding="utf-8")
        ai_fallback = ROOT.joinpath("teacher_app", "assessments", "free_ai_fallback.py").read_text(encoding="utf-8")
        ai_jobs = ROOT.joinpath("teacher_app", "assessments", "ai_jobs.py").read_text(encoding="utf-8")
        script_jobs = ROOT.joinpath("teacher_app", "materials", "media_script_jobs.py").read_text(encoding="utf-8")
        audio_jobs = ROOT.joinpath("teacher_app", "materials", "media_audio_jobs.py").read_text(encoding="utf-8")
        subtitle_jobs = ROOT.joinpath("teacher_app", "materials", "media_subtitle_jobs.py").read_text(encoding="utf-8")
        presentation_jobs = ROOT.joinpath("teacher_app", "materials", "ai_presentation_jobs.py").read_text(encoding="utf-8")
        video_jobs = ROOT.joinpath("teacher_app", "materials", "ai_video_jobs.py").read_text(encoding="utf-8")
        notification_prefs = ROOT.joinpath("teacher_app", "notifications", "preferences.py").read_text(encoding="utf-8")
        ai_worker = ROOT.joinpath("ai_question_worker.py").read_text(encoding="utf-8")
        storage_service = ROOT.joinpath("teacher_app", "storage", "service.py").read_text(encoding="utf-8")
        storage_worker = ROOT.joinpath("teacher_app", "storage", "worker_runtime.py").read_text(encoding="utf-8")
        storage_web = ROOT.joinpath("teacher_app", "storage", "web_runtime.py").read_text(encoding="utf-8")
        storage_admin = ROOT.joinpath("teacher_app", "storage", "admin_service.py").read_text(encoding="utf-8")
        incidents_source = ROOT.joinpath("teacher_app", "notifications", "incidents.py").read_text(encoding="utf-8")
        account_self_service = ROOT.joinpath("teacher_app", "auth", "self_service.py").read_text(encoding="utf-8")
        upload_progress = ROOT.joinpath("teacher_app", "materials", "upload_progress.py").read_text(encoding="utf-8")
        notification_events = ROOT.joinpath("teacher_app", "notifications", "events.py").read_text(encoding="utf-8")
        command_center = ROOT.joinpath("teacher_app", "command_center", "service.py").read_text(encoding="utf-8")
        delivery_routes = ROOT.joinpath("teacher_app", "materials", "delivery_routes.py").read_text(encoding="utf-8")
        sync_upload = ROOT.joinpath("teacher_app", "materials", "sync_upload.py").read_text(encoding="utf-8")
        protocol_version = ROOT.joinpath("teacher_app", "worker", "protocol_version.py").read_text(encoding="utf-8")
        privacy_source = ROOT.joinpath("teacher_app", "common", "privacy.py").read_text(encoding="utf-8")

        for marker, source in (
            ("R2 upload session status count failed", r2),
            ("R2 stale upload session lookup failed", r2),
            ("R2 stale upload remote cleanup failed", r2),
            ("R2 stale upload state transition failed", r2),
            ("email notification claim release failed", reminders),
            ("email reminder event projection failed", reminders),
            ("operational incident reminder send failed", reminders),
            ("operational incident sync failed", reminders),\n            ("operational metrics sample failed", reminders),
            ("PGY template temp cleanup failed", pgy),
            ("PGY EPA reference import failed", pgy),
            ("PGY template delete failed", pgy),
            ("material category label lookup failed", materials),
            ("scope resource lookup failed", scope_filter),
            ("scope authorization resolution denied", scope_filter),
            ("AI provider attempt failed", ai_fallback),
            ("AI question job failed", ai_jobs),
            ("AI media script job failed", script_jobs),
            ("AI media audio job failed", audio_jobs),
            ("AI media audio preview URL failed", audio_jobs),
            ("AI media subtitle job failed", subtitle_jobs),
            ("AI presentation job failed", presentation_jobs),
            ("AI video job failed", video_jobs),
            ("notification preferences read fallback", notification_prefs),
            ("storage best-effort delete failed", storage_service),
            ("storage cleanup failed backend=mega", storage_worker),
            ("storage cleanup failed backend=gdrive", storage_worker),
            ("storage read failed backend=mega", storage_web),
            ("storage preview cache cleanup failed backend=mega", storage_web),
            ("storage status failed backend=gdrive", storage_admin),
            ("storage migration failed target=r2", storage_admin),
            ("storage migration rollback failed backend=r2", storage_admin),
            ("operational incident persistence unavailable", incidents_source),
            ("operational incident read failed", incidents_source),
            ("operational incident AI projection failed", incidents_source),
            ("password reset email send failed", account_self_service),
            ("material upload progress write failed", upload_progress),
            ("material upload progress read fallback", upload_progress),
            ("notification exam deadline projection failed", notification_events),
            ("notification exam window lookup failed", notification_events),
            ("command center learner projection failed", command_center),
            ("command center review projection failed", command_center),
            ("command center material failure projection failed", command_center),
            ("command center assignment projection failed", command_center),
            ("command center draft projection failed", command_center),
            ("material question image remote read failed", delivery_routes),
            ("material classification text extraction fallback", sync_upload),
            ("worker protocol heartbeat lookup failed", protocol_version),
            ("AI privacy material lookup failed", privacy_source),
        ):
            self.assertIn(marker, source)

        for source in (
            r2, reminders, pgy, materials, scope_filter, ai_fallback, ai_jobs,
            script_jobs, audio_jobs, subtitle_jobs, presentation_jobs, video_jobs,
            notification_prefs, storage_service, storage_worker, storage_web,
            storage_admin, incidents_source, account_self_service, upload_progress,
            notification_events, command_center, delivery_routes, sync_upload,
            protocol_version, privacy_source,
        ):
            self.assertIn("error_type=%s", source)
        self.assertIn("loop error type=", ai_worker)
        self.assertNotIn('loop error: {str(exc)', ai_worker)


    def test_material_error_taxonomy_classifies_common_worker_failures(self):
        cases = (
            ("Temporary failure in name resolution", "下載原始檔", "DNS_RESOLUTION"),
            ("LibreOffice conversion failed", "轉檔處理", "LIBREOFFICE_CONVERSION"),
            ("ffmpeg encoder failed", "轉檔處理", "FFMPEG_CONVERSION"),
            ("Cloudflare R2 AccessDenied", "正式發布", "R2_STORAGE"),
            ("psycopg database connection failed", "完成確認", "DATABASE"),
            ("Worker 下載檔案 SHA256 不符。", "驗證教材", "SOURCE_INTEGRITY"),
        )
        for message, stage, expected in cases:
            with self.subTest(expected=expected):
                result = error_observability.classify_material_error(message, stage=stage, status="failed")
                self.assertEqual(result["errorCode"], expected)
                self.assertTrue(result["errorMessage"])
                self.assertTrue(result["errorAction"])

    def test_material_error_taxonomy_covers_worker_heartbeat_states(self):
        stalled = error_observability.classify_material_error("", status="processing", observability_state="stalled")
        delayed = error_observability.classify_material_error("", status="processing", observability_state="heartbeat_delayed")
        self.assertEqual(stalled["errorCode"], "WORKER_HEARTBEAT_STALLED")
        self.assertEqual(delayed["errorCode"], "WORKER_HEARTBEAT_DELAYED")

    def test_material_error_technical_detail_redacts_secrets(self):
        raw = "Authorization: Bearer abc123 password=hunter2 https://user:secret@example.com/path?token=xyz"
        safe = error_observability.sanitize_technical_detail(raw)
        self.assertNotIn("abc123", safe)
        self.assertNotIn("hunter2", safe)
        self.assertNotIn(":secret@", safe)
        self.assertNotIn("token=xyz", safe)
        self.assertIn("***", safe)


if __name__ == "__main__":
    unittest.main()
