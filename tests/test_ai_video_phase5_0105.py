from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from teacher_app.materials import ai_video_jobs, ai_video_quality as quality, ai_video_runtime
from teacher_app.materials.ai_video_routes import _effective_quality


class AiVideoPhase5MigrationTests(unittest.TestCase):
    def test_0105_is_additive_and_adds_quality_idempotency_snapshot(self):
        from teacher_app.maintenance.ai_video_migration import ai_presentation_videos_101
        from teacher_app.maintenance.ai_video_phase5_migration import ai_video_production_hardening_105

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        ai_presentation_videos_101(conn, "sqlite")
        conn.execute(
            "INSERT INTO ai_video_jobs(id,presentation_id,presentation_family_id,presentation_revision,group_key,training_area,actor_username,status,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            ("old-job", "ppt-1", "fam", 1, "g", "a", "teacher", "completed", "x", "x"),
        )
        ai_video_production_hardening_105(conn, "sqlite")
        job_cols = {row[1] for row in conn.execute("PRAGMA table_info(ai_video_jobs)")}
        video_cols = {row[1] for row in conn.execute("PRAGMA table_info(ai_presentation_videos)")}
        pub_cols = {row[1] for row in conn.execute("PRAGMA table_info(ai_video_publications)")}
        self.assertIn("idempotency_key", job_cols)
        self.assertTrue({"quality_manifest_json", "render_metrics_json", "render_ruleset_version", "frame_renderer"}.issubset(video_cols))
        self.assertTrue({"snapshot_json", "video_family_id", "video_revision_number"}.issubset(pub_cols))
        self.assertEqual(conn.execute("SELECT status FROM ai_video_jobs WHERE id='old-job'").fetchone()[0], "completed")
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(ai_video_jobs)")}
        self.assertIn("idx_ai_video_jobs_idempotency", indexes)


class AiVideoPhase5QualityTests(unittest.TestCase):
    def test_generation_key_is_stable_checksum_voice_and_ruleset_bound(self):
        presentation = {
            "id": "ppt-1", "presentationFamilyId": "fam", "revisionNumber": 4,
            "artifactSha256": "a" * 64,
        }
        first = quality.generation_key(presentation, voice="zf_xiaoxiao")
        self.assertEqual(first, quality.generation_key(dict(presentation), voice="zf_xiaoxiao"))
        self.assertNotEqual(first, quality.generation_key(presentation, voice="zm_yunxi"))
        self.assertTrue(first.startswith("vidgen-"))

    def test_fallback_renderer_is_warning_but_timeline_mismatch_is_blocking(self):
        slides = [{"id": "s1"}]
        timeline = [{"slideId": "s1", "start": 0.0, "end": 1.0}]
        manifest = quality.evaluate_render(
            prepared_slides=slides, timeline=timeline, vtt_text="WEBVTT\n\n00:00.000 --> 00:01.000\nA",
            srt_text="1\n00:00:00,000 --> 00:00:01,000\nA", frame_renderer="text-fallback",
            presentation_sha256="a" * 64,
        )
        self.assertEqual(manifest["status"], "warning")
        self.assertIn("FRAME_RENDERER_FALLBACK", {item["code"] for item in manifest["warnings"]})

        blocked = quality.evaluate_render(
            prepared_slides=slides * 2, timeline=timeline, vtt_text="WEBVTT\n\n00:00.000 --> 00:01.000\nA",
            srt_text="1\n00:00:00,000 --> 00:00:01,000\nA", frame_renderer="powerpoint-com",
            presentation_sha256="a" * 64,
        )
        self.assertEqual(blocked["status"], "error")
        self.assertIn("TIMELINE_COUNT_MISMATCH", {item["code"] for item in blocked["errors"]})

    def test_legacy_video_requires_warning_acknowledgement_semantics(self):
        manifest = _effective_quality({"qualityManifest": {}, "renderRulesetVersion": ""})
        self.assertEqual(manifest["status"], "warning")
        self.assertIn("LEGACY_QUALITY_UNVERIFIED", {item["code"] for item in manifest["warnings"]})


class AiVideoPhase5RuntimeTests(unittest.TestCase):
    def test_phase4_cover_and_continuation_pages_align_video_timeline_source(self):
        presentation = {
            "title": "CBC 教學",
            "slides": [
                {"id": "s1", "enabled": True, "title": "長內容", "bullets": [f"重點 {i}" for i in range(1, 9)], "speakerNotes": "老師原始講稿"},
                {"id": "s2", "enabled": True, "title": "表格", "bullets": [], "speakerNotes": "表格講稿", "blocks": [{"type": "table", "headers": ["項目", "值"], "rows": [[str(i), str(i)] for i in range(8)]}]},
            ],
        }
        slides = ai_video_runtime._prepared_slides(presentation)
        self.assertEqual(slides[0]["id"], "phase4-cover")
        self.assertEqual(len(slides), 5)
        continuation = [item for item in slides if item["id"] not in {"phase4-cover", "s1", "s2"}]
        self.assertTrue(continuation)
        self.assertTrue(all(not item.get("speakerNotes") for item in continuation))

    def test_fallback_narration_includes_table_and_comparison_content(self):
        table = ai_video_runtime.narration_for_slide({
            "title": "QC", "blocks": [{"type": "table", "headers": ["項目", "結果"], "rows": [["Westgard", "通過"]]}]
        })
        self.assertIn("Westgard", table)
        compare = ai_video_runtime.narration_for_slide({
            "title": "比較", "blocks": [{"type": "comparison", "leftTitle": "舊", "leftItems": ["人工"], "rightTitle": "新", "rightItems": ["AI 輔助"]}]
        })
        self.assertIn("AI 輔助", compare)

    def test_non_windows_powerpoint_export_fails_closed_to_runtime_fallback(self):
        if ai_video_runtime.os.name == "nt":
            self.skipTest("This regression covers non-Windows CI behavior.")
        self.assertEqual(ai_video_runtime._export_powerpoint_frames(Path("missing.pptx"), Path("missing-frames")), [])


class AiVideoPhase5QueueTests(unittest.TestCase):
    def test_duplicate_generation_replays_before_rate_limits(self):
        presentation = {"id": "ppt-1", "presentationFamilyId": "fam", "revisionNumber": 1, "artifactSha256": "a" * 64}
        actor = {"username": "teacher"}
        existing = {"id": "vidjob-existing", "status": "completed"}
        with (
            patch.object(ai_video_jobs.VideoStorage, "capability", return_value={"available": True}),
            patch.object(ai_video_jobs.repository, "get_job_by_idempotency_key", return_value=existing),
            patch.object(ai_video_jobs, "_enforce_limits") as limits,
        ):
            result = ai_video_jobs.enqueue({"voice": "zf_xiaoxiao"}, actor, presentation)
        self.assertEqual(result["id"], "vidjob-existing")
        limits.assert_not_called()

    def test_failed_video_retry_is_bounded_repository_operation(self):
        with patch.object(ai_video_jobs.repository, "retry_failed_job", return_value={"id": "vidjob-1", "status": "queued"}) as retry:
            result = ai_video_jobs.retry({"id": "vidjob-1"})
        self.assertEqual(result["status"], "queued")
        retry.assert_called_once()


class AiVideoPhase5SourceContractTests(unittest.TestCase):
    def test_routes_keep_scope_quality_gate_and_no_legacy_admin_key(self):
        routes = Path("teacher_app/materials/ai_video_routes.py").read_text(encoding="utf-8")
        runtime = Path("teacher_app/materials/ai_video_runtime.py").read_text(encoding="utf-8")
        bootstrap = Path("setup_teacher_worker.ps1").read_text(encoding="utf-8")
        self.assertIn("load", runtime.lower())
        self.assertIn("PresentationStorage", runtime)
        self.assertIn("PowerPoint.Application", runtime)
        self.assertIn("requiresWarningAcknowledgement", routes)
        self.assertIn("qualityBlocked", routes)
        self.assertIn("/quality", routes)
        self.assertIn("/retry", routes)
        self.assertIn("_scope(owner", routes)
        self.assertNotIn("X-Admin-Key", routes)
        self.assertNotIn("getAdminKey", routes)
        self.assertIn("requirements-ai-worker.txt", bootstrap)
        self.assertIn("Ensure-FFmpeg", bootstrap)
        self.assertIn("Install-WorkerTasks", bootstrap)


if __name__ == "__main__":
    unittest.main()
