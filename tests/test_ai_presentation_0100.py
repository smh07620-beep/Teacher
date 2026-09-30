from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from teacher_app.materials.ai_presentation_routes import _presentation_allowed
from teacher_app.maintenance.ai_presentation_migration import (
    ai_presentation_production_hardening_100,
    ai_presentations_99,
)
from teacher_app.materials.ai_presentation_repository import publication_receipt_key
from teacher_app.materials.ai_presentation_runtime import (
    normalize_slides,
    parse_slide_outline,
    render_pptx,
)
from teacher_app.materials.ai_presentation_storage import PresentationStorage


class AiPresentationMigrationTests(unittest.TestCase):
    def test_fresh_0099_then_0100_creates_required_tables(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        ai_presentations_99(conn, "sqlite")
        ai_presentation_production_hardening_100(conn, "sqlite")
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        self.assertIn("ai_presentation_templates", tables)
        self.assertIn("ai_presentation_jobs", tables)
        self.assertIn("ai_presentations", tables)
        self.assertIn("ai_presentation_publications", tables)

    def test_0100_upgrades_local_only_0099_additively(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            "CREATE TABLE ai_presentation_templates ("
            "id TEXT PRIMARY KEY,name TEXT NOT NULL,group_key TEXT NOT NULL,training_area TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE ai_presentations ("
            "id TEXT PRIMARY KEY,title TEXT NOT NULL,group_key TEXT NOT NULL,training_area TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO ai_presentations(id,title,group_key,training_area) VALUES(?,?,?,?)",
            ("legacy-ppt", "Legacy", "grpBio", "internal"),
        )
        ai_presentation_production_hardening_100(conn, "sqlite")
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(ai_presentations)").fetchall()
        }
        self.assertTrue(
            {
                "presentation_family_id",
                "parent_version_id",
                "revision_number",
                "artifact_backend",
                "artifact_storage_key",
                "artifact_sha256",
                "artifact_bytes",
                "artifact_mime_type",
                "published_at",
            }.issubset(columns)
        )
        row = conn.execute("SELECT id,title FROM ai_presentations WHERE id='legacy-ppt'").fetchone()
        self.assertEqual((row["id"], row["title"]), ("legacy-ppt", "Legacy"))


class AiPresentationRuntimeTests(unittest.TestCase):
    def test_numbered_bullets_are_not_misread_as_slide_headers(self):
        slides = parse_slide_outline(
            "第 1 張：CBC 概念\n1. WBC\n2. RBC\n第 2 張：判讀\n- 先確認 QC\n- 再判讀結果"
        )
        self.assertEqual(len(slides), 2)
        self.assertEqual(slides[0]["title"], "CBC 概念")
        self.assertEqual(slides[0]["bullets"], ["WBC", "RBC"])

    def test_teacher_slide_controls_normalize_order_and_enabled(self):
        slides = normalize_slides(
            [
                {"id": "b", "order": 9, "enabled": False, "title": "B", "bullets": ["x"]},
                {"id": "a", "order": 2, "enabled": True, "title": "A", "bullets": ["y"]},
            ]
        )
        self.assertEqual([item["order"] for item in slides], [1, 2])
        self.assertFalse(slides[0]["enabled"])
        self.assertTrue(slides[1]["enabled"])

    def test_rendered_pptx_contains_allowlisted_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "test.pptx"
            render_pptx(
                title="AI Test",
                slides=[{"title": "Slide", "bullets": ["Point"], "enabled": True}],
                output_path=output,
                provenance={
                    "sourceMaterialId": "mat-1",
                    "sourceDraftId": "draft-1",
                    "sourceJobId": "job-1",
                    "sourceChunkIds": ["chunk-1"],
                    "teacherApprovedBy": "teacher-a",
                    "teacherApprovedAt": "2026-09-30T00:00:00+00:00",
                },
            )
            self.assertGreater(output.stat().st_size, 1024)
            from pptx import Presentation

            rendered = Presentation(str(output))
            self.assertIn("mat-1", rendered.core_properties.comments)
            self.assertNotIn("token=", rendered.core_properties.comments.lower())

    def test_local_storage_is_fail_closed_without_explicit_development_opt_in(self):
        with patch.dict(
            os.environ,
            {
                "AI_PRESENTATION_STORAGE_BACKEND": "local",
                "AI_PRESENTATION_ALLOW_LOCAL_STORAGE": "false",
            },
            clear=False,
        ):
            with self.assertRaises(RuntimeError):
                PresentationStorage().backend()

    def test_publication_receipt_key_is_deterministic(self):
        first = publication_receipt_key("ppt-1", "mat-1")
        second = publication_receipt_key("ppt-1", "mat-1")
        self.assertEqual(first, second)
        self.assertNotEqual(first, publication_receipt_key("ppt-1", "mat-2"))


class AiPresentationRbacTests(unittest.TestCase):
    def test_system_admin_can_operate_but_cannot_teacher_approve(self):
        user = {"role": "system_admin"}
        self.assertTrue(_presentation_allowed(user, "presentation.create"))
        self.assertTrue(_presentation_allowed(user, "presentation.edit"))
        self.assertFalse(_presentation_allowed(user, "presentation.approve"))
        self.assertTrue(_presentation_allowed(user, "presentation.publish"))

    def test_teacher_and_group_leader_have_full_presentation_permissions(self):
        for role in ("clinical_teacher", "group_leader"):
            user = {"role": role}
            self.assertTrue(_presentation_allowed(user, "presentation.create"))
            self.assertTrue(_presentation_allowed(user, "presentation.edit"))
            self.assertTrue(_presentation_allowed(user, "presentation.approve"))
            self.assertTrue(_presentation_allowed(user, "presentation.publish"))

    def test_education_admin_cannot_teacher_approve(self):
        user = {"role": "education_admin"}
        self.assertTrue(_presentation_allowed(user, "presentation.create"))
        self.assertTrue(_presentation_allowed(user, "presentation.edit"))
        self.assertFalse(_presentation_allowed(user, "presentation.approve"))
        self.assertTrue(_presentation_allowed(user, "presentation.publish"))


if __name__ == "__main__":
    unittest.main()
