import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask, g

import release_contract
from teacher_app.frontend.assets import ASSET_MANIFEST
from teacher_app.materials import media_audio_jobs, media_script_jobs, media_script_runtime
from teacher_app.materials.ai_material_routes import register_ai_material_routes


ROOT = Path(__file__).resolve().parents[1]


class AIMaterialMigration97Tests(unittest.TestCase):
    def test_release_contract_advances_after_content_audience(self):
        self.assertIn("0097-ai-material-drafts", release_contract.REQUIRED_MIGRATIONS)
        self.assertLess(
            release_contract.REQUIRED_MIGRATIONS.index("0096-content-audience-scope"),
            release_contract.REQUIRED_MIGRATIONS.index("0097-ai-material-drafts"),
        )

    def test_sqlite_migration_generalizes_reviewed_drafts_without_second_store(self):
        # Keep migration imports out of module discovery. The global migration
        # registry is intentionally populated by the factory in release order;
        # importing 0097 while unittest is still collecting modules can append
        # it before 0094 has created media_scripts and make unrelated factory
        # tests fail during bootstrap.
        from teacher_app.maintenance.media_script_migration import media_script_jobs_94
        from teacher_app.maintenance.ai_material_migration import ai_material_drafts_97

        conn = sqlite3.connect(":memory:")
        try:
            media_script_jobs_94(conn, "sqlite")
            ai_material_drafts_97(conn, "sqlite")
            columns = {row[1] for row in conn.execute("PRAGMA table_info(media_scripts)")}
            self.assertTrue(
                {"draft_type", "provider", "model", "fallback_used", "publication_material_id"} <= columns
            )
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertNotIn("ai_material_drafts", tables)
        finally:
            conn.close()


class AIMaterialRuntime97Tests(unittest.TestCase):
    def test_prepare_request_reuses_media_script_queue_for_multiple_output_types(self):
        material = {"id": "mat-1", "group": "grpBio", "area": "internal", "active": False}
        actor = {"username": "teacher1"}
        with patch.object(media_script_jobs.material_repository, "get_material", return_value=material):
            values = media_script_jobs.prepare_request(
                {"materialId": "mat-1", "outputType": "summary", "focus": "QC"}, actor
            )
        self.assertEqual(values["request"]["outputType"], "summary")
        self.assertEqual(values["group_key"], "grpBio")
        with patch.object(media_script_jobs.material_repository, "get_material", return_value=material):
            with self.assertRaisesRegex(ValueError, "不支援"):
                media_script_jobs.prepare_request(
                    {"materialId": "mat-1", "outputType": "auto_publish"}, actor
                )

    def test_prepare_request_keeps_secondary_authoring_sources_for_worker_rag(self):
        material = {"id": "mat-1", "group": "grpBio", "area": "internal", "active": False}
        with patch.object(media_script_jobs.material_repository, "get_material", return_value=material):
            values = media_script_jobs.prepare_request(
                {"materialId": "mat-1", "referenceMaterialIds": ["mat-2", "mat-3", "mat-2"]}, {"username": "teacher1"}
            )
        self.assertEqual(values["request"]["referenceMaterialIds"], ["mat-2", "mat-3"])

    def test_prompt_is_source_grounded_and_requires_teacher_review_for_general_drafts(self):
        prompt = media_script_runtime._prompt(
            source_title="QC SOP",
            context="QC 異常時依文件執行複檢。",
            focus="異常處理",
            tone="clinical",
            target_minutes=5,
            output_type="summary",
        )
        self.assertIn("不得加入教材來源沒有支持的醫療事實", prompt)
        self.assertIn("【需教師補充】", prompt)
        self.assertIn("需由教師確認後方可發布", prompt)
        self.assertIn("重點摘要", prompt)

    def test_audio_accepts_approved_script_from_inactive_authoring_source(self):
        script = {
            "id": "script-1", "draftType": "script", "status": "approved",
            "materialId": "mat-1", "group": "grpBio", "area": "internal",
        }
        source = {"id": "mat-1", "group": "grpBio", "area": "internal", "active": False}
        with patch.object(media_audio_jobs.media_script_repository, "get_script", return_value=script), \
             patch.object(media_audio_jobs.material_repository, "get_material", return_value=source):
            values = media_audio_jobs.prepare_request(
                {"scriptId": "script-1", "voice": "zf_xiaoxiao"}, {"username": "teacher1"}
            )
        self.assertEqual(values["material_id"], "mat-1")

    def test_audio_rejects_non_script_ai_draft(self):
        draft = {
            "id": "draft-1", "draftType": "summary", "status": "approved",
            "materialId": "mat-1", "group": "grpBio", "area": "internal",
        }
        with patch.object(media_audio_jobs.media_script_repository, "get_script", return_value=draft):
            with self.assertRaisesRegex(ValueError, "只有教學講稿"):
                media_audio_jobs.prepare_request(
                    {"scriptId": "draft-1"}, {"username": "teacher1"}
                )


class AIMaterialRoute97Tests(unittest.TestCase):
    def _app(self, group="grpBio"):
        app = Flask(__name__)
        app.secret_key = "test"

        @app.before_request
        def bind_user():
            g.teacher_user = {
                "username": "teacher1",
                "role": "clinical_teacher",
                "roles": ["clinical_teacher"],
                "preferredArea": "internal",
                "preferredGroup": group,
            }

        register_ai_material_routes(app)
        return app

    def test_generate_queues_existing_worker_path_and_never_runs_ai_in_web(self):
        app = self._app("grpBio")
        material = {"id": "mat-1", "group": "grpBio", "area": "internal", "active": False}
        queued = {
            "id": "msjob-97", "materialId": "mat-1", "group": "grpBio", "area": "internal",
            "status": "queued", "request": {"outputType": "summary"},
            "progressPercent": 0, "progressStage": "等待 AI 教材草稿", "progressDetail": "工作已排入 AI 佇列",
            "createdAt": "", "updatedAt": "", "startedAt": "", "completedAt": "",
        }
        with app.test_client() as client, \
             patch("teacher_app.materials.ai_material_routes.material_repository.get_material", return_value=material), \
             patch("teacher_app.materials.ai_material_routes._ai_worker_online_error", return_value=None), \
             patch("teacher_app.materials.ai_material_routes.media_script_jobs.enqueue", return_value=queued) as enqueue, \
             patch("teacher_app.materials.ai_material_routes.audit.record_event"):
            response = client.post(
                "/api/ai-material-drafts/generate",
                json={"materialId": "mat-1", "outputType": "summary"},
            )
        self.assertEqual(response.status_code, 202)
        enqueue.assert_called_once()
        self.assertEqual(response.get_json()["jobId"], "msjob-97")

    def test_generate_denies_teacher_outside_group_scope(self):
        app = self._app("grpBio")
        material = {"id": "mat-2", "group": "grpBB", "area": "internal", "active": False}
        with app.test_client() as client, \
             patch("teacher_app.materials.ai_material_routes.material_repository.get_material", return_value=material):
            response = client.post(
                "/api/ai-material-drafts/generate",
                json={"materialId": "mat-2", "outputType": "handout"},
            )
        self.assertEqual(response.status_code, 403)


class AIMaterialFrontend97Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROOT.joinpath("static", "teacher-ai-material-1014.js").read_text(encoding="utf-8")
        cls.factory = ROOT.joinpath("teacher_app", "factory.py").read_text(encoding="utf-8")
        cls.audio = ROOT.joinpath("teacher_app", "materials", "media_audio_jobs.py").read_text(encoding="utf-8")

    def test_asset_is_after_canonical_upload_transport(self):
        body = ASSET_MANIFEST["system"]["body"]
        self.assertIn("/teacher-ai-material-1014.js", body)
        self.assertLess(body.index("/material-upload-client.js"), body.index("/teacher-ai-material-1014.js"))

    def test_teacher_flow_has_upload_six_outputs_review_and_explicit_publish(self):
        for marker in (
            "MaterialUploadClient.enqueue",
            "/api/ai-material-drafts/generate",
            "教學講義",
            "重點摘要",
            "投影片大綱",
            "教學講稿",
            "測驗題草稿",
            "課程學習目標",
            "✅ 教師核准",
            "📚 發布成教材",
            "active:false",
        ):
            self.assertIn(marker, self.source)
        self.assertNotIn("/api/ai-material-drafts/auto-publish", self.source)

    def test_powerpoint_authoring_prefers_multi_file_draft_sources_over_existing_material(self):
        for marker in (
            "multiple class=\"mt-1 block w-full text-sm\"",
            "AI 來源內容工作台",
            "authoringSourceIds",
            "referenceMaterialIds: allAuthoringSourceIds()",
            "或選擇既有教材（可多選）",
            "active:false",
        ):
            self.assertIn(marker, self.source)

    def test_factory_registers_migration_and_routes_before_runtime_use(self):
        self.assertIn("ai_material_migration", self.factory)
        self.assertIn("register_ai_material_routes", self.factory)
        self.assertLess(self.factory.index("ai_material_migration"), self.factory.index("register_schema_migrations(app)"))

    def test_narration_is_strictly_limited_to_approved_script_type(self):
        self.assertIn("draftType", self.audio)
        self.assertIn("只有教學講稿類型可以產生 AI 語音", self.audio)
        self.assertIn("只有已核准講稿可以產生 AI 語音", self.audio)


if __name__ == "__main__":
    unittest.main()
