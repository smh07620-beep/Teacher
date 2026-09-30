from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from teacher_app.materials import ai_presentation_quality as quality


class AiPresentationPhase4QualityTests(unittest.TestCase):
    def test_auto_layout_is_deterministic_and_allowlisted(self):
        slide = {"layout": "evil-layout", "title": "A", "bullets": ["x"], "blocks": [{"type": "table"}]}
        self.assertEqual(quality.select_layout(slide), "table")
        self.assertIn(quality.select_layout({"title": "B", "bullets": ["x"], "blocks": []}), {"content"})

    def test_text_overflow_becomes_continuation_slides(self):
        slides = [{
            "id": "s1", "enabled": True, "title": "Dense", "layout": "content", "blocks": [],
            "bullets": ["內容" * 180, "第二點" * 100, "第三點" * 100], "speakerNotes": "",
        }]
        prepared, manifest = quality.prepare_slides(slides, provenance_present=True)
        self.assertGreater(len(prepared), 1)
        self.assertIn("TEXT_SPLIT", {item["code"] for item in manifest["warnings"]})
        self.assertTrue(any("續" in item["title"] for item in prepared[1:]))

    def test_table_pagination_preserves_headers(self):
        headers = ["項目", "值"]
        rows = [[f"R{i}", str(i)] for i in range(15)]
        slides = [{"id":"s1","enabled":True,"title":"Table","bullets":[],"layout":"table",
                   "blocks":[{"type":"table","headers":headers,"rows":rows}],"speakerNotes":""}]
        prepared, manifest = quality.prepare_slides(slides, provenance_present=True)
        self.assertEqual(len(prepared), 3)
        self.assertTrue(all(item["blocks"][0]["headers"] == headers for item in prepared))
        self.assertEqual(sum(len(item["blocks"][0]["rows"]) for item in prepared), 15)
        self.assertIn("TABLE_SPLIT", {item["code"] for item in manifest["warnings"]})

    def test_comparison_pagination_does_not_truncate_items(self):
        left = [f"L{i}" for i in range(12)]
        right = [f"R{i}" for i in range(9)]
        slides = [{"id":"s1","enabled":True,"title":"Compare","bullets":[],"layout":"comparison",
                   "blocks":[{"type":"comparison","leftItems":left,"rightItems":right}],"speakerNotes":""}]
        prepared, manifest = quality.prepare_slides(slides, provenance_present=True)
        self.assertEqual(sum(len(item["blocks"][0]["leftItems"]) for item in prepared), len(left))
        self.assertEqual(sum(len(item["blocks"][0]["rightItems"]) for item in prepared), len(right))
        self.assertIn("COMPARISON_SPLIT", {item["code"] for item in manifest["warnings"]})

    def test_missing_image_is_warning_not_arbitrary_url(self):
        prepared, manifest = quality.prepare_slides([
            {"id":"s1","enabled":True,"title":"Image","bullets":[],"layout":"image",
             "blocks":[{"type":"image","altText":"missing"}],"speakerNotes":""}
        ], provenance_present=True)
        self.assertEqual(len(prepared), 1)
        self.assertEqual(manifest["status"], "warning")
        self.assertIn("MISSING_IMAGE", {item["code"] for item in manifest["warnings"]})

    def test_missing_provenance_is_blocking_error(self):
        _prepared, manifest = quality.prepare_slides([
            {"id":"s1","enabled":True,"title":"A","bullets":["x"],"layout":"content","blocks":[],"speakerNotes":""}
        ], provenance_present=False)
        self.assertEqual(manifest["status"], "error")
        self.assertIn("PROVENANCE_MISSING", {item["code"] for item in manifest["errors"]})

    def test_placeholder_map_accepts_only_semantic_selectors(self):
        self.assertEqual(
            quality.sanitize_placeholder_map({"title":"title","body":"body","evil":"shape-7","image":"Picture Placeholder 9"}),
            {"title":"title","body":"body"},
        )

    def test_regenerate_key_is_stable_and_ruleset_bound(self):
        item = {"id":"ppt-1","presentationFamilyId":"fam","revisionNumber":2,"templateId":"tpl","slides":[{"title":"A"}]}
        self.assertEqual(quality.regenerate_key(item), quality.regenerate_key(dict(item)))
        self.assertTrue(quality.regenerate_key(item).startswith("pptregen-"))

    def test_phase4_sources_keep_publish_gate_scope_and_no_legacy_admin_key(self):
        routes = Path("teacher_app/materials/ai_presentation_routes.py").read_text(encoding="utf-8")
        repository = Path("teacher_app/materials/ai_presentation_repository.py").read_text(encoding="utf-8")
        frontend = Path("static/teacher-ai-presentation-1016.js").read_text(encoding="utf-8")
        self.assertIn("/quality", routes)
        self.assertIn("/regenerate", routes)
        self.assertIn("load_scoped(presentation_id, user)", routes)
        self.assertIn("requiresWarningAcknowledgement", routes)
        self.assertIn("qualityBlocked", routes)
        self.assertIn("idempotency_key", repository)
        self.assertIn("Phase 4", frontend)
        self.assertNotIn("X-Admin-Key", routes + frontend)
        self.assertNotIn("getAdminKey", routes + frontend)


class AiPresentationPhase4MigrationTests(unittest.TestCase):
    def test_0104_is_additive(self):
        from teacher_app.maintenance.ai_presentation_phase4_migration import ai_presentation_quality_automation_104

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE ai_presentations(id TEXT PRIMARY KEY,title TEXT NOT NULL)")
        conn.execute("CREATE TABLE ai_presentation_jobs(id TEXT PRIMARY KEY,status TEXT NOT NULL DEFAULT 'queued')")
        conn.execute("INSERT INTO ai_presentations(id,title) VALUES(?,?)", ("ppt-old", "Old"))
        ai_presentation_quality_automation_104(conn, "sqlite")
        pcols = {row[1] for row in conn.execute("PRAGMA table_info(ai_presentations)").fetchall()}
        jcols = {row[1] for row in conn.execute("PRAGMA table_info(ai_presentation_jobs)").fetchall()}
        self.assertTrue({"quality_manifest_json","render_metrics_json","render_ruleset_version"}.issubset(pcols))
        self.assertIn("idempotency_key", jcols)
        self.assertEqual(conn.execute("SELECT title FROM ai_presentations WHERE id='ppt-old'").fetchone()[0], "Old")
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(ai_presentation_jobs)").fetchall()}
        self.assertIn("idx_ai_presentation_jobs_idempotency", indexes)


if __name__ == "__main__":
    unittest.main()
