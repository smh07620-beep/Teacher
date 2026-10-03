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

        for marker, source in (
            ("R2 upload session status count failed", r2),
            ("R2 stale upload session lookup failed", r2),
            ("R2 stale upload remote cleanup failed", r2),
            ("R2 stale upload state transition failed", r2),
            ("email notification claim release failed", reminders),
            ("email reminder event projection failed", reminders),
            ("worker offline reminder send failed", reminders),
            ("PGY template temp cleanup failed", pgy),
            ("PGY EPA reference import failed", pgy),
            ("PGY template delete failed", pgy),
            ("material category label lookup failed", materials),
            ("scope resource lookup failed", scope_filter),
            ("scope authorization resolution denied", scope_filter),
        ):
            self.assertIn(marker, source)

        for source in (r2, reminders, pgy, materials, scope_filter):
            self.assertIn("error_type=%s", source)


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
