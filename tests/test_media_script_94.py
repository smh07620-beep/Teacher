import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask, g

import release_contract
from teacher_app.frontend.assets import ASSET_MANIFEST
from teacher_app.maintenance.media_script_migration import media_script_jobs_94
from teacher_app.materials import media_script_runtime
from teacher_app.materials.media_script_routes import register_media_script_routes


ROOT = Path(__file__).resolve().parents[1]


class MediaScriptMigration94Tests(unittest.TestCase):
    def test_release_contract_contains_0094(self):
        self.assertIn("0094-media-script-jobs", release_contract.REQUIRED_MIGRATIONS)
        self.assertIn("0095-media-audio-jobs", release_contract.REQUIRED_MIGRATIONS)
        self.assertLess(
            release_contract.REQUIRED_MIGRATIONS.index("0094-media-script-jobs"),
            release_contract.REQUIRED_MIGRATIONS.index("0095-media-audio-jobs"),
        )

    def test_sqlite_migration_creates_separate_job_and_script_tables(self):
        conn = sqlite3.connect(":memory:")
        try:
            media_script_jobs_94(conn, "sqlite")
            names = {
                row[0]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            self.assertIn("media_script_jobs", names)
            self.assertIn("media_scripts", names)
            job_columns = {row[1] for row in conn.execute("PRAGMA table_info(media_script_jobs)")}
            script_columns = {row[1] for row in conn.execute("PRAGMA table_info(media_scripts)")}
            self.assertTrue({"claim_token", "request_json", "result_json", "status"} <= job_columns)
            self.assertTrue({"body", "status", "approved_by", "approved_at", "source_chunks_json"} <= script_columns)
        finally:
            conn.close()


class MediaScriptRuntime94Tests(unittest.TestCase):
    def test_generation_is_source_grounded_and_requires_teacher_review(self):
        entry = {"id": "mat-1", "title": "抗體鑑定", "filename": "source.pdf"}
        chunks = [{
            "materialId": "mat-1", "materialTitle": "抗體鑑定", "chunkId": "mat-1:chunk-0001",
            "section": "第 1 頁", "text": "步驟一：確認反應型態。", "terms": {"步驟", "反應"},
        }]
        settings = type("Settings", (), {"provider": "groq"})()
        with patch.object(media_script_runtime.ai_runtime, "ai_settings", return_value=settings), \
             patch.object(media_script_runtime.ai_runtime, "active_ai_provider", return_value="groq"), \
             patch.object(media_script_runtime.ai_runtime, "ai_model_name", return_value="test-model"), \
             patch.object(media_script_runtime.ai_runtime, "extract_material_text_for_ai", return_value=("步驟一：確認反應型態。" * 10, 120)), \
             patch.object(media_script_runtime.ai_runtime, "build_retrieval_chunks", return_value=chunks), \
             patch.object(media_script_runtime.ai_runtime, "format_retrieval_context", return_value="【來源】步驟一：確認反應型態。"), \
             patch.object(media_script_runtime.ai_privacy, "external_enabled", return_value=True), \
             patch.object(media_script_runtime, "_groq", return_value="抗體鑑定教學講稿內容。" * 10):
            result = media_script_runtime.generate_script(entry, target_minutes=5)
        self.assertTrue(result["requiresTeacherReview"])
        self.assertEqual(result["sourceMaterialId"], "mat-1")
        self.assertEqual(result["sourceChunks"][0]["chunkId"], "mat-1:chunk-0001")
        self.assertEqual(result["provider"], "groq")
        self.assertEqual(result["model"], "test-model")

    def test_prompt_forbids_inventing_medical_content(self):
        prompt = media_script_runtime._prompt(
            source_title="教材", context="來源", focus="", tone="clinical", target_minutes=5
        )
        self.assertIn("不得加入教材來源沒有支持的醫療事實", prompt)
        self.assertIn("【需教師補充】", prompt)
        self.assertIn("需由授課教師確認", prompt)


class MediaScriptRoute94Tests(unittest.TestCase):
    def _app(self, group="grpBio"):
        app = Flask(__name__)
        app.secret_key = "test"

        @app.before_request
        def bind_user():
            g.teacher_user = {
                "username": "teacher1",
                "role": "clinical_teacher",
                "roles": ["clinical_teacher"],
                "preferredGroup": group,
            }

        register_media_script_routes(app)
        return app

    def test_generate_is_group_scoped_and_queues_instead_of_running_ai_in_web(self):
        app = self._app("grpBio")
        material = {"id": "mat-1", "group": "grpBio", "area": "internal", "active": True}
        queued = {
            "id": "msjob-1", "materialId": "mat-1", "group": "grpBio", "area": "internal",
            "status": "queued", "progressPercent": 0, "progressStage": "等待產生講稿",
            "progressDetail": "工作已排入 AI 佇列", "createdAt": "", "updatedAt": "", "startedAt": "", "completedAt": "",
        }
        with app.test_client() as client, \
             patch("teacher_app.materials.media_script_routes.material_repository.get_material", return_value=material), \
             patch("teacher_app.materials.media_script_routes._ai_worker_online_error", return_value=None), \
             patch("teacher_app.materials.media_script_routes.media_script_jobs.enqueue", return_value=queued) as enqueue, \
             patch("teacher_app.materials.media_script_routes.audit.record_event"):
            response = client.post("/api/media-scripts/generate", json={"materialId": "mat-1", "targetMinutes": 5})
        self.assertEqual(response.status_code, 202)
        enqueue.assert_called_once()
        self.assertEqual(response.get_json()["jobId"], "msjob-1")

    def test_generate_accepts_private_extra_narration_sources(self):
        app = self._app("grpBio")
        materials = {
            "mat-main": {"id": "mat-main", "group": "grpBio", "area": "internal", "active": True},
            "mat-extra": {"id": "mat-extra", "group": "grpBio", "area": "internal", "active": False},
        }
        queued = {
            "id": "msjob-extra", "materialId": "mat-main", "group": "grpBio", "area": "internal",
            "status": "queued", "request": {"outputType": "script", "referenceMaterialIds": ["mat-extra"]},
            "progressPercent": 0, "progressStage": "等待產生講稿", "progressDetail": "",
            "createdAt": "", "updatedAt": "", "startedAt": "", "completedAt": "",
        }
        captured = {}

        def enqueue(body, _user):
            captured.update(body)
            return queued

        with app.test_client() as client, \
             patch("teacher_app.materials.media_script_routes.material_repository.get_material", side_effect=lambda material_id: materials.get(material_id)), \
             patch("teacher_app.materials.media_script_routes._ai_worker_online_error", return_value=None), \
             patch("teacher_app.materials.media_script_routes.media_script_jobs.enqueue", side_effect=enqueue), \
             patch("teacher_app.materials.media_script_routes.audit.record_event"):
            response = client.post(
                "/api/media-scripts/generate",
                json={"materialId": "mat-main", "referenceMaterialIds": ["mat-extra", "mat-extra"]},
            )
        self.assertEqual(response.status_code, 202, response.get_data(as_text=True))
        self.assertEqual(captured["referenceMaterialIds"], ["mat-extra"])

    def test_generate_denies_teacher_outside_group_scope(self):
        app = self._app("grpBio")
        material = {"id": "mat-2", "group": "grpBB", "area": "internal", "active": True}
        with app.test_client() as client, \
             patch("teacher_app.materials.media_script_routes.material_repository.get_material", return_value=material):
            response = client.post("/api/media-scripts/generate", json={"materialId": "mat-2"})
        self.assertEqual(response.status_code, 403)


class MediaScriptFrontend94Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROOT.joinpath("static", "teacher-media-script-1014.js").read_text(encoding="utf-8")
        cls.worker = ROOT.joinpath("ai_question_worker.py").read_text(encoding="utf-8")

    def test_script_studio_asset_is_loaded(self):
        body = ASSET_MANIFEST["system"]["body"]
        self.assertIn("/teacher-media-script-1014.js", body)
        self.assertLess(body.index("/teacher-workspace-1014.js"), body.index("/teacher-media-script-1014.js"))

    def test_frontend_requires_explicit_teacher_approval(self):
        for marker in (
            "/api/media-scripts/generate",
            "/api/media-scripts/jobs/",
            "💾 儲存草稿",
            "✅ 教師核准講稿",
            "核准後才可作為下一階段 AI 語音／影片的正式來源",
        ):
            self.assertIn(marker, self.source)

    def test_ai_worker_fairly_services_question_script_and_audio_queues(self):
        self.assertIn("MediaScriptJobProcessor", self.worker)
        self.assertIn("MediaAudioJobProcessor", self.worker)
        self.assertIn("question_processor.run_next_queued()", self.worker)
        self.assertIn("script_processor.run_next_queued()", self.worker)
        self.assertIn("audio_processor.run_next_queued()", self.worker)
        queue_calls = [
            "question_processor.run_next_queued()",
            "script_processor.run_next_queued()",
            "presentation_processor.run_next_queued()",
            "video_processor.run_next_queued()",
            "audio_processor.run_next_queued()",
            "subtitle_processor.run_next_queued()",
        ]
        positions = [self.worker.index(marker) for marker in queue_calls]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("Give every domain queue one chance per loop", self.worker)

    def test_frontend_does_not_fake_tts_or_auto_publish(self):
        self.assertNotIn("speechSynthesis.speak", self.source)
        self.assertNotIn("/api/media-scripts/publish", self.source)
        self.assertNotIn("X-Admin-Key", self.source)


if __name__ == "__main__":
    unittest.main()
