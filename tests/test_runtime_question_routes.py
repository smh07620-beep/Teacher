import io
import socket
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask, g, jsonify

from teacher_app.assessments import runtime_question_routes
from teacher_app.assessments.question_runtime import QuestionRuntime


class _Base:
    AI_MAX_QUESTIONS = 15
    AI_SOURCE_MAX_CHARS = 50000
    AI_MAX_MATERIALS = 4
    FREE_ONLY_MODE = True

    def __init__(self, root: Path, db_path: str):
        self.app = Flask(__name__ + str(id(self)))
        self.app.config.update(TESTING=True, SECRET_KEY="runtime-question-test")
        self.db_path = db_path
        self.user = {"username": "teacher", "role": "education_admin"}
        self.QUESTION_IMAGES_DIR = root / "question-images"
        self.QUESTION_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        self.materials = {
            "mat-1": {"id": "mat-1", "active": True, "group": "grpBio", "area": "internal"}
        }
        self.progress = []

    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, "sqlite"

    def _current_user(self):
        return self.user

    def require_admin(self):
        return None

    def active_material_backend(self):
        return "local"

    def ai_question_is_configured(self):
        return True

    def active_ai_provider(self):
        return "groq"

    def ai_model_name(self):
        return "test-model"

    def get_material(self, material_id):
        return self.materials.get(material_id)

    def clear_upload_progress(self, progress_id):
        self.progress.append(("clear", progress_id))

    def set_upload_progress(self, progress_id, percent, stage, detail):
        self.progress.append((progress_id, percent, stage, detail))

    def generate_ai_questions_from_materials(self, materials, **kwargs):
        self.last_generate = (materials, kwargs)
        return ([{"question": "AI 題", "options": ["A", "B"], "correct": 0}], "教材", ["text"])

    def _infer_ai_strategy(self, _materials):
        return "balanced"


class RuntimeQuestionRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.db_path = str(root / "questions.sqlite")
        self.base = _Base(root, self.db_path)
        self._create_schema()
        self.db_patch = patch(
            "teacher_app.common.db.get_connection",
            side_effect=self.base.connect,
        )
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)

        @self.base.app.get("/api/quiz-questions", endpoint="api_list_quiz_questions")
        def legacy_list():
            return jsonify({"legacy": True})

        runtime_question_routes.register_runtime_question_routes(self.base)
        self.client = self.base.app.test_client()

    def _create_schema(self):
        conn, _ = self.base.connect()
        try:
            conn.executescript(
                """
                CREATE TABLE quiz_categories (
                    id TEXT PRIMARY KEY, group_key TEXT NOT NULL, training_area TEXT NOT NULL,
                    course_id TEXT NOT NULL DEFAULT '', title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
                    sort_order INTEGER NOT NULL DEFAULT 0, date_added TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1,
                    blind_mode INTEGER NOT NULL DEFAULT 0, draw_count INTEGER NOT NULL DEFAULT 0,
                    passing_score INTEGER NOT NULL DEFAULT 80, audience TEXT NOT NULL DEFAULT '', draw_rules TEXT NOT NULL DEFAULT '{}',
                    review_status TEXT NOT NULL DEFAULT 'approved', reviewer_name TEXT NOT NULL DEFAULT '',
                    reviewed_at TEXT NOT NULL DEFAULT '', published_at TEXT NOT NULL DEFAULT '',
                    publication_id TEXT NOT NULL DEFAULT '', publication_hash TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE quiz_questions (
                    id TEXT PRIMARY KEY, quiz_category_id TEXT NOT NULL, tag TEXT NOT NULL DEFAULT '',
                    question TEXT NOT NULL, question_type TEXT NOT NULL DEFAULT 'choice', difficulty TEXT NOT NULL DEFAULT 'standard',
                    image_url TEXT NOT NULL DEFAULT '', options TEXT NOT NULL DEFAULT '[]', correct INTEGER NOT NULL DEFAULT 0,
                    answer_config TEXT NOT NULL DEFAULT '{}', explanation TEXT NOT NULL DEFAULT '',
                    sort_order INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1
                );
                INSERT INTO quiz_categories(
                    id,group_key,training_area,title,active,draw_count,draw_rules,review_status
                ) VALUES('cat-1','grpBio','internal','考卷',1,1,'{}','approved');
                INSERT INTO quiz_questions(
                    id,quiz_category_id,tag,question,question_type,difficulty,image_url,options,correct,answer_config,explanation,sort_order,active
                ) VALUES('q-seed','cat-1','一般','種子題','choice','standard','','["A","B"]',0,'{}','',0,1);
                """
            )
        finally:
            conn.close()

    def test_exact_urls_endpoints_and_existing_view_is_replaced(self):
        expected = {
            ("/api/quiz-question-images", "api_upload_question_image", "POST"),
            ("/api/quiz-questions/random", "api_random_quiz_questions", "GET"),
            ("/api/quiz-questions", "api_list_quiz_questions", "GET"),
            ("/api/quiz-questions/admin", "api_admin_list_quiz_questions", "GET"),
            ("/api/quiz-questions", "api_create_quiz_question", "POST"),
            ("/api/quiz-questions/<question_id>", "api_update_quiz_question", "PATCH"),
            ("/api/quiz-questions/<question_id>", "api_delete_quiz_question", "DELETE"),
            ("/api/quiz-questions/batch", "api_batch_update_quiz_questions", "PATCH"),
            ("/api/quiz-questions/batch-delete", "api_batch_delete_quiz_questions", "POST"),
            ("/api/quiz-questions/import-url", "api_import_quiz_questions_url", "POST"),
            ("/api/ai-questions/status", "api_ai_question_status", "GET"),
            ("/api/ai-questions/generate", "api_ai_generate_questions", "POST"),
            ("/api/ai-questions/import", "api_ai_import_questions", "POST"),
        }
        actual = set()
        for rule in self.base.app.url_map.iter_rules():
            for method in set(rule.methods) - {"HEAD", "OPTIONS"}:
                actual.add((rule.rule, rule.endpoint, method))
        self.assertTrue(expected.issubset(actual), sorted(expected - actual))
        self.assertEqual(
            self.base.app.view_functions["api_list_quiz_questions"].__module__,
            runtime_question_routes.__name__,
        )
        response = self.client.get("/api/quiz-questions?category=cat-1")
        self.assertIsInstance(response.get_json(), list)

    def test_public_list_keeps_legacy_login_contract(self):
        self.base.user = None
        response = self.client.get("/api/quiz-questions?category=cat-1")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.get_json(),
            {"error": "請先登入後再使用教材。", "loginRequired": True},
        )

    def test_create_update_batch_and_delete_invalidate_review(self):
        created = self.client.post(
            "/api/quiz-questions",
            json={
                "quizCategoryId": "cat-1",
                "question": "新題",
                "questionType": "choice",
                "options": ["A", "B"],
                "correct": 1,
                "answerConfig": {"reviewSource": {"materialId": "mat-1", "anchorType": "page", "page": 3}},
            },
        )
        self.assertEqual(created.status_code, 200, created.get_data(as_text=True))
        question_id = created.get_json()["id"]
        self.assertEqual(created.get_json()["answerConfig"]["reviewSource"]["page"], 3)

        conn, _ = self.base.connect()
        try:
            category = conn.execute("SELECT review_status,active FROM quiz_categories WHERE id='cat-1'").fetchone()
        finally:
            conn.close()
        self.assertEqual(category["review_status"], "draft")
        self.assertEqual(category["active"], 0)

        updated = self.client.patch(
            f"/api/quiz-questions/{question_id}",
            json={"question": "更新題"},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.get_json()["question"]["question"], "更新題")

        batched = self.client.patch(
            "/api/quiz-questions/batch",
            json={"items": [{"id": question_id, "data": {"tag": "批次"}}]},
        )
        self.assertEqual(batched.status_code, 200)
        self.assertEqual(batched.get_json()["count"], 1)

        deleted = self.client.delete(f"/api/quiz-questions/{question_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.get_json(), {"ok": True})

    def test_random_and_admin_list_preserve_shapes(self):
        random_response = self.client.get("/api/quiz-questions/random?category=cat-1")
        self.assertEqual(random_response.status_code, 200)
        self.assertEqual(len(random_response.get_json()), 1)
        admin = self.client.get("/api/quiz-questions/admin?category=cat-1")
        self.assertEqual(admin.status_code, 200)
        self.assertEqual(admin.get_json()[0]["id"], "q-seed")

    def test_scoped_question_manager_cannot_cross_group(self):
        self.base.user = {
            "username": "teacher",
            "role": "clinical_teacher",
            "preferredGroup": "grpMicro",
        }
        response = self.client.get("/api/quiz-questions/admin?category=cat-1")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json(), {"error": "此資源不在你的授權範圍。"})

    def test_image_upload_uses_legacy_storage_boundary(self):
        response = self.client.post(
            "/api/quiz-question-images",
            data={"file": (io.BytesIO(b"image-bytes"), "sample.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        url = response.get_json()["url"]
        self.assertTrue(url.startswith("/question-images/"))
        self.assertTrue((self.base.QUESTION_IMAGES_DIR / Path(url).name).is_file())

    def test_ai_status_generate_and_import_contracts(self):
        status = self.client.get("/api/ai-questions/status")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.get_json()["provider"], "groq")
        self.assertEqual(status.get_json()["maxMaterials"], 4)

        with patch.object(
            runtime_question_routes.material_repository,
            "get_material",
            side_effect=self.base.get_material,
        ):
            generated = self.client.post(
                "/api/ai-questions/generate",
                json={"quizCategoryId": "cat-1", "materialIds": ["mat-1"], "progressId": "p-1"},
            )
        self.assertEqual(generated.status_code, 200, generated.get_data(as_text=True))
        self.assertEqual(generated.get_json()["strategyApplied"], "balanced")
        self.assertEqual(generated.get_json()["sourceCount"], 1)
        self.assertIn(("clear", "p-1"), self.base.progress)
        self.assertTrue(any(item[:3] == ("p-1", 2, "準備 AI 出題") for item in self.base.progress if len(item) >= 3))
        self.assertTrue(any(item[:3] == ("p-1", 100, "AI 候選題完成") for item in self.base.progress if len(item) >= 3))

        imported = self.client.post(
            "/api/ai-questions/import",
            json={
                "quizCategoryId": "cat-1",
                "questions": [{"question": "AI 匯入題", "questionType": "choice", "options": ["A", "B"], "correct": 0}],
            },
        )
        self.assertEqual(imported.status_code, 200, imported.get_data(as_text=True))
        self.assertEqual(imported.get_json()["imported"], 1)
        self.assertEqual(len(imported.get_json()["questions"]), 1)

    def test_import_url_rejects_private_address_before_fetch(self):
        with patch(
            "teacher_app.assessments.runtime_question_routes.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))],
        ):
            response = self.client.post(
                "/api/quiz-questions/import-url",
                json={"quizCategoryId": "cat-1", "url": "http://example.test/questions.json"},
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "基於安全性，不允許讀取內網或本機網址")

    def test_batch_delete_preserves_strict_legacy_admin_boundary(self):
        response = self.client.post(
            "/api/quiz-questions/batch-delete",
            json={"ids": ["q-seed"]},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json(), {"error": "權限不足：此功能限教學管理者使用。"})

        self.base.user = {"username": "root", "role": "system_admin"}
        allowed = self.client.post(
            "/api/quiz-questions/batch-delete",
            json={"ids": ["q-seed"]},
        )
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.get_json()["count"], 1)

    def test_direct_flask_app_uses_request_actor_and_explicit_question_runtime(self):
        root = Path(self.tmp.name) / "direct"
        question_images = root / "question-images"
        progress_dir = root / "progress"
        question_images.mkdir(parents=True)
        progress_dir.mkdir(parents=True)
        actor = {"username": "teacher", "role": "education_admin"}
        generated_calls = []

        class LocalStorage:
            @staticmethod
            def active_backend():
                return "local"

        runtime = QuestionRuntime(
            ai_question_is_configured=lambda: True,
            active_ai_provider=lambda: "groq",
            ai_model_name=lambda: "direct-model",
            generate_ai_questions_from_materials=lambda materials, **kwargs: (
                generated_calls.append((materials, kwargs))
                or ([{"question": "AI 題", "options": ["A", "B"], "correct": 0}], "教材", ["text"])
            ),
            infer_ai_strategy=lambda materials: "balanced",
            paths_provider=lambda: type("Paths", (), {
                "question_images_dir": question_images,
                "upload_progress_dir": progress_dir,
            })(),
            storage_adapter=LocalStorage(),
            max_materials=4,
        )
        app = Flask("runtime-question-direct")
        app.config.update(TESTING=True, SECRET_KEY="test")

        @app.before_request
        def bind_actor():
            g.teacher_user = actor

        runtime_question_routes.register_runtime_question_routes(app, runtime=runtime)
        client = app.test_client()
        status = client.get("/api/ai-questions/status")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.get_json()["model"], "direct-model")

        image = client.post(
            "/api/quiz-question-images",
            data={"file": (io.BytesIO(b"image"), "direct.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(image.status_code, 200)
        self.assertTrue((question_images / Path(image.get_json()["url"]).name).exists())

        with patch.object(
            runtime_question_routes.repository,
            "get_category_full",
            return_value={"id": "cat-direct", "group": "grpBio", "area": "internal", "active": True},
        ), patch.object(
            runtime_question_routes.material_repository,
            "get_material",
            return_value={"id": "mat-direct", "group": "grpBio", "area": "internal", "active": True},
        ):
            generated = client.post(
                "/api/ai-questions/generate",
                json={"quizCategoryId": "cat-direct", "materialIds": ["mat-direct"], "progressId": "direct-p"},
            )
        self.assertEqual(generated.status_code, 200, generated.get_data(as_text=True))
        self.assertEqual(len(generated_calls), 1)
        self.assertTrue((progress_dir / "direct-p.json").exists())

        def fail_generate(*_args, **_kwargs):
            raise RuntimeError("generation failed")

        runtime.generate_ai_questions_from_materials = fail_generate
        with patch.object(
            runtime_question_routes.repository,
            "get_category_full",
            return_value={"id": "cat-direct", "group": "grpBio", "area": "internal", "active": True},
        ), patch.object(
            runtime_question_routes.material_repository,
            "get_material",
            return_value={"id": "mat-direct", "group": "grpBio", "area": "internal", "active": True},
        ):
            failed = client.post(
                "/api/ai-questions/generate",
                json={"quizCategoryId": "cat-direct", "materialIds": ["mat-direct"], "progressId": "failed-p"},
            )
        self.assertEqual(failed.status_code, 400)
        self.assertEqual(failed.get_json(), {"error": "generation failed"})
        progress = runtime._progress_store().read("failed-p")
        self.assertEqual(progress["percent"], 0)
        self.assertEqual(progress["stage"], "AI 出題失敗")

    def test_question_image_mega_failure_preserves_502_and_cleans_local_file(self):
        root = Path(self.tmp.name) / "mega-image"
        question_images = root / "question-images"
        progress_dir = root / "progress"
        question_images.mkdir(parents=True)
        progress_dir.mkdir(parents=True)

        class FailingMegaStorage:
            @staticmethod
            def active_backend():
                return "mega"

            @staticmethod
            def _mega_free_guard(_size):
                raise RuntimeError("quota full")

            @staticmethod
            def _mega_remote_join(*parts):
                return "/".join(str(part).strip("/") for part in parts)

            @staticmethod
            def _mega_root():
                return "/root"

            @staticmethod
            def _mega_upload_file(*_args):
                raise AssertionError("upload must not run after free guard failure")

        runtime = QuestionRuntime(
            ai_question_is_configured=lambda: False,
            active_ai_provider=lambda: "groq",
            ai_model_name=lambda: "model",
            generate_ai_questions_from_materials=lambda *_args, **_kwargs: ([], "", []),
            infer_ai_strategy=lambda _materials: "auto",
            paths_provider=lambda: type("Paths", (), {
                "question_images_dir": question_images,
                "upload_progress_dir": progress_dir,
            })(),
            storage_adapter=FailingMegaStorage(),
        )
        app = Flask("runtime-question-mega")
        app.config.update(TESTING=True, SECRET_KEY="test")

        @app.before_request
        def bind_actor():
            g.teacher_user = {"username": "teacher", "role": "education_admin"}

        runtime_question_routes.register_runtime_question_routes(app, runtime=runtime)
        response = app.test_client().post(
            "/api/quiz-question-images",
            data={"file": (io.BytesIO(b"image"), "mega.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.get_json(), {"error": "題目影像上傳 MEGA 失敗：quota full"})
        self.assertEqual(list(question_images.iterdir()), [])

    def test_runtime_route_source_has_no_broad_base_or_provider_credentials(self):
        source = Path(runtime_question_routes.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "base.",
            "legacy_host",
            "GROQ_API_KEY",
            "GEMINI_API_KEY",
            "OPENAI_API_KEY",
            "generate_ai_questions_from_materials =",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
