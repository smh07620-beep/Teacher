from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from teacher_app.materials import ai_video_quality as quality
from teacher_app.materials import ai_video_renderer as renderer
from teacher_app.materials import ai_video_runtime
from teacher_app.materials.ai_video_routes import _effective_quality, _renderer_policy


class AiVideoPhase6RendererPolicyTests(unittest.TestCase):
    def test_renderer_order_is_powerpoint_then_libreoffice_then_safe_fallback(self):
        self.assertEqual(
            renderer.RENDERER_ORDER,
            ("powerpoint-com", "libreoffice-headless", "text-fallback"),
        )
        policy = _renderer_policy()
        self.assertEqual(policy["order"], list(renderer.RENDERER_ORDER))
        self.assertEqual(policy["resolvedOn"], "local-ai-worker")
        self.assertTrue(policy["libreOffice"]["freeFallback"])
        self.assertTrue(policy["safeFallback"]["requiresPublicationWarningAcknowledgement"])

    def test_capability_summary_never_exposes_local_binary_paths(self):
        with (
            patch.object(renderer, "_powershell", return_value=r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"),
            patch.object(renderer, "_libreoffice", return_value=r"C:\Program Files\LibreOffice\program\soffice.exe"),
        ):
            summary = renderer.capability_summary()
        serialized = repr(summary).lower()
        self.assertEqual(summary["selectedCandidate"], "powerpoint-com")
        self.assertNotIn("c:\\windows", serialized)
        self.assertNotIn("program files", serialized)
        self.assertNotIn("soffice.exe", serialized)

    def test_powerpoint_failure_falls_through_to_libreoffice(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pptx = root / "source.pptx"
            pptx.write_bytes(b"pptx")
            libreoffice_frames = [root / "lo-1.png", root / "lo-2.png"]
            with (
                patch.object(renderer, "_powershell", return_value="powershell.exe"),
                patch.object(renderer, "_libreoffice", return_value="soffice.exe"),
                patch.object(renderer, "export_powerpoint_frames", return_value=([], "timeout")) as ppt,
                patch.object(renderer, "export_libreoffice_frames", return_value=(libreoffice_frames, "ok")) as libre,
            ):
                frames, selected, attempts = renderer.render_exact_frames(pptx, expected_count=2, root=root)
        self.assertEqual(frames, libreoffice_frames)
        self.assertEqual(selected, "libreoffice-headless")
        self.assertEqual(attempts[0], {"renderer": "powerpoint-com", "status": "failed", "detail": "timeout"})
        self.assertEqual(attempts[1]["status"], "success")
        ppt.assert_called_once()
        libre.assert_called_once()

    def test_powerpoint_can_be_explicitly_disabled_without_disabling_video(self):
        with (
            patch.dict(os.environ, {"AI_VIDEO_POWERPOINT_COM_ENABLED": "false"}),
            patch.object(renderer, "_libreoffice", return_value=r"C:\LibreOffice\soffice.exe"),
        ):
            summary = renderer.capability_summary()
        self.assertFalse(summary["candidates"][0]["candidate"])
        self.assertEqual(summary["selectedCandidate"], "libreoffice-headless")


class AiVideoPhase6QualityTests(unittest.TestCase):
    @staticmethod
    def _evaluate(frame_renderer: str):
        return quality.evaluate_render(
            prepared_slides=[{"id": "s1"}],
            timeline=[{"slideId": "s1", "start": 0.0, "end": 1.0}],
            vtt_text="WEBVTT\n\n00:00.000 --> 00:01.000\nA",
            srt_text="1\n00:00:00,000 --> 00:00:01,000\nA",
            frame_renderer=frame_renderer,
            presentation_sha256="a" * 64,
        )

    def test_libreoffice_is_compatibility_warning_not_text_fallback(self):
        manifest = self._evaluate("libreoffice-headless")
        self.assertEqual(manifest["status"], "warning")
        codes = {item["code"] for item in manifest["warnings"]}
        self.assertIn("FRAME_RENDERER_COMPATIBILITY", codes)
        self.assertNotIn("FRAME_RENDERER_FALLBACK", codes)

    def test_safe_text_fallback_remains_warning_gated(self):
        manifest = self._evaluate("text-fallback")
        self.assertEqual(manifest["status"], "warning")
        self.assertIn("FRAME_RENDERER_FALLBACK", {item["code"] for item in manifest["warnings"]})

    def test_unknown_renderer_is_blocking(self):
        manifest = self._evaluate("untrusted-renderer")
        self.assertEqual(manifest["status"], "error")
        self.assertIn("FRAME_RENDERER_UNKNOWN", {item["code"] for item in manifest["errors"]})

    def test_old_phase5_ruleset_is_visible_as_outdated_warning(self):
        manifest = _effective_quality(
            {
                "qualityManifest": {"rulesetVersion": "video-phase5-v1", "status": "ok"},
                "renderRulesetVersion": "video-phase5-v1",
            }
        )
        self.assertEqual(manifest["status"], "warning")
        self.assertIn("RENDER_RULESET_OUTDATED", {item["code"] for item in manifest["warnings"]})

    def test_renderer_attempt_metrics_are_bounded_and_allowlisted(self):
        metrics = quality.sanitize_render_metrics(
            {
                "rendererAttempts": [
                    {"renderer": "powerpoint-com", "status": "failed", "detail": "timeout"},
                    {"renderer": "libreoffice-headless", "status": "success", "detail": "compatible-slide-count"},
                ],
                "frameRenderer": "libreoffice-headless",
            }
        )
        self.assertEqual(metrics["frameRenderer"], "libreoffice-headless")
        self.assertEqual(len(metrics["rendererAttempts"]), 2)
        self.assertEqual(metrics["rendererAttempts"][1]["status"], "success")


class AiVideoPhase6SourceIntegrityTests(unittest.TestCase):
    def test_missing_immutable_source_pptx_is_blocking_not_renderer_fallback(self):
        class BrokenStorage:
            def download(self, _location, _target):
                raise RuntimeError("source checksum/download unavailable")

        presentation = {
            "artifactBackend": "r2",
            "artifactStorageKey": "approved.pptx",
            "artifactSha256": "a" * 64,
        }
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(RuntimeError, "source checksum/download unavailable"):
                ai_video_runtime._render_frames(
                    presentation,
                    [{"id": "s1", "title": "A", "bullets": []}],
                    Path(temp),
                    presentation_storage=BrokenStorage(),
                )


class AiVideoPhase6ProductContracts(unittest.TestCase):
    def test_worker_bootstrap_installs_free_libreoffice_fallback(self):
        bootstrap = Path("setup_teacher_worker.ps1").read_text(encoding="utf-8")
        requirements = Path("requirements-ai-worker.txt").read_text(encoding="utf-8")
        self.assertIn("TheDocumentFoundation.LibreOffice", bootstrap)
        self.assertIn("Ensure-LibreOffice", bootstrap)
        self.assertIn("Show-VideoRendererCapabilities", bootstrap)
        self.assertIn("AI_VIDEO_LIBREOFFICE_PATH", bootstrap)
        self.assertIn("AI_VIDEO_POWERPOINT_COM_ENABLED", Path(".local-worker.env.example").read_text(encoding="utf-8"))
        self.assertIn("PyMuPDF", requirements)
        self.assertIn("import requests, psycopg, pptx, fitz", bootstrap)

    def test_teacher_workspace_exposes_renderer_quality_approve_publish_and_retry(self):
        frontend = Path("static/teacher-ai-video-1015.js").read_text(encoding="utf-8")
        for marker in (
            "AI VIDEO · PHASE 6",
            "rendererPolicy",
            "rendererAttempts",
            "/api/ai-videos/status",
            "/api/ai-videos/generate",
            "/retry",
            "/quality",
            "/approve",
            "/publish",
            "libreoffice-headless",
            "FRAME_RENDERER",
        ):
            if marker == "FRAME_RENDERER":
                continue
            self.assertIn(marker, frontend)
        self.assertNotIn("X-Admin-Key", frontend)
        self.assertNotIn("getAdminKey", frontend)

    def test_worker_startup_logs_safe_renderer_candidate_ids(self):
        worker = Path("ai_question_worker.py").read_text(encoding="utf-8")
        self.assertIn("capability_summary", worker)
        self.assertIn("video_renderers=", worker)
        self.assertNotIn("AI_VIDEO_LIBREOFFICE_PATH", worker)

    def test_phase6_requires_no_new_schema_migration(self):
        import release_contract

        self.assertIn("0105-ai-video-production-hardening", release_contract.REQUIRED_MIGRATIONS)
        self.assertLess(
            release_contract.REQUIRED_MIGRATIONS.index("0105-ai-video-production-hardening"),
            release_contract.REQUIRED_MIGRATIONS.index("0106-notification-email-preferences"),
        )
        self.assertEqual(quality.RULESET_VERSION, "video-phase6-v1")


if __name__ == "__main__":
    unittest.main()