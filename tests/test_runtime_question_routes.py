import io
import socket
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask, g, jsonify

from teacher_app.assessments import ai_job_schema, ai_jobs, runtime_question_routes
from teacher_app.assessments.question_runtime import QuestionRuntime


ROOT = Path(__file__).resolve().parents[1]


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
                    sort_order INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'published', origin TEXT NOT NULL DEFAULT 'manual',
                    reviewed_by TEXT NOT NULL DEFAULT '', reviewed_at TEXT NOT NULL DEFAULT '',
                    version INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL DEFAULT '', normalized_hash TEXT NOT NULL DEFAULT ''
                );
                INSERT INTO quiz_categories(
                    id,group_key,training_area,title,active,draw_count,draw_rules,review_status
                ) VALUES('cat-1','grpBio','internal','考卷',1,1,'{}','approved');
                INSERT INTO quiz_questions(
                    id,quiz_category_id,tag,question,question_type,difficulty,image_url,options,correct,answer_config,explanation,sort_order,active
                ) VALUES('q-seed','cat-1','一般','種子題','choice','standard','','["A","B"]',0,'{}','',0,1);
                """
            )
            ai_job_schema.init_schema(conn, "sqlite")
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
            ("/api/ai-questions/jobs/<job_id>", "api_ai_question_job", "GET"),
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

    def test_ai_job_status_is_scope_checked(self):
        with patch.object(
            runtime_question_routes.material_repository,
            "get_material",
            side_effect=self.base.get_material,
        ):
            queued = self.client.post(
                "/api/ai-questions/generate",
                json={"quizCategoryId": "cat-1", "materialIds": ["mat-1"]},
            )
        self.assertEqual(queued.status_code, 202, queued.get_data(as_text=True))
        self.base.user = {
            "username": "teacher",
            "role": "clinical_teacher",
            "preferredGroup": "grpMicro",
        }
        response = self.client.get(f"/api/ai-questions/jobs/{queued.get_json()['jobId']}")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json(), {"error": "此資源不在你的授權範圍。"})

    def test_ai_enqueue_limits_active_jobs_per_actor(self):
        with patch.dict("os.environ", {"AI_QUESTION_JOB_MAX_ACTIVE_PER_USER": "1"}), patch.object(
            runtime_question_routes.material_repository,
            "get_material",
            side_effect=self.base.get_material,
        ):
            first = self.client.post(
                "/api/ai-questions/generate",
                json={"quizCategoryId": "cat-1", "materialIds": ["mat-1"]},
            )
            second = self.client.post(
                "/api/ai-questions/generate",
                json={"quizCategoryId": "cat-1", "materialIds": ["mat-1"]},
            )
        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 429)
        self.assertIn("排隊或執行中", second.get_json()["error"])

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
                json={"quizCategoryId": "cat-1", "materialIds": ["mat-1"]},
            )
            self.assertEqual(generated.status_code, 202, generated.get_data(as_text=True))
            job_id = generated.get_json()["jobId"]
            queued = self.client.get(f"/api/ai-questions/jobs/{job_id}")
            self.assertEqual(queued.status_code, 200)
            self.assertEqual(queued.get_json()["status"], "queued")
            processor = ai_jobs.AiQuestionJobProcessor(
                runtime_question_routes.runtime_from_owner(self.base)
            )
            self.assertTrue(processor.run_job(job_id))
        job = self.client.get(f"/api/ai-questions/jobs/{job_id}")
        self.assertEqual(job.status_code, 200, job.get_data(as_text=True))
        self.assertEqual(job.get_json()["status"], "completed")
        self.assertEqual(job.get_json()["result"]["strategyApplied"], "balanced")
        self.assertEqual(job.get_json()["result"]["sourceCount"], 1)
        self.assertEqual(job.get_json()["progress"]["percent"], 100)

        imported = self.client.post(
            "/api/ai-questions/import",
            json={
                "quizCategoryId": "cat-1",
                "questions": [{
                    "question": "AI 匯入題",
                    "questionType": "choice",
                    "options": ["A", "B"],
                    "correct": 0,
                    "sourceMaterialId": "mat-1",
                    "chunkId": "mat-1:chunk-0003",
                    "sourceEvidence": "教材第三段直接支持答案。",
                    "answerConfig": {
                        "reviewSource": {
                            "materialId": "mat-1",
                            "materialTitle": "教材",
                            "anchorType": "section",
                            "section": "mat-1:chunk-0003",
                            "reviewHint": "教材第三段直接支持答案。",
                        }
                    },
                }],
            },
        )
        self.assertEqual(imported.status_code, 200, imported.get_data(as_text=True))
        self.assertEqual(imported.get_json()["imported"], 1)
        self.assertEqual(len(imported.get_json()["questions"]), 1)
        self.assertEqual(imported.get_json()["questions"][0]["status"], "draft")
        self.assertEqual(imported.get_json()["questions"][0]["origin"], "ai_generated")
        review_source = imported.get_json()["questions"][0]["answerConfig"]["reviewSource"]
        self.assertEqual(review_source["materialId"], "mat-1")
        self.assertEqual(review_source["section"], "mat-1:chunk-0003")
        conn, _ = self.base.connect()
        try:
            category = conn.execute(
                "SELECT review_status,active FROM quiz_categories WHERE id='cat-1'"
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(category["review_status"], "draft")
        self.assertEqual(category["active"], 0)

    def test_external_video_url_uses_canonical_media_validation(self):
        created = self.client.post(
            "/api/quiz-questions",
            json={
                "quizCategoryId": "cat-1",
                "question": "影片題",
                "questionType": "choice",
                "options": ["A", "B"],
                "correct": 0,
                "answerConfig": {
                    "mediaUrl": "https://youtu.be/dQw4w9WgXcQ",
                    "pauseAt": 12,
                },
            },
        )
        self.assertEqual(created.status_code, 200, created.get_data(as_text=True))
        self.assertEqual(
            created.get_json()["answerConfig"]["mediaUrl"],
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )

        rejected = self.client.post(
            "/api/quiz-questions",
            json={
                "quizCategoryId": "cat-1",
                "question": "不安全影片題",
                "questionType": "choice",
                "options": ["A", "B"],
                "correct": 0,
                "answerConfig": {"mediaUrl": "http://127.0.0.1/video.mp4"},
            },
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertIn("HTTPS", rejected.get_json()["error"])

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

    def test_import_url_rejects_non_http_scheme_before_dns(self):
        with patch(
            "teacher_app.assessments.runtime_question_routes.socket.getaddrinfo",
        ) as resolver:
            response = self.client.post(
                "/api/quiz-questions/import-url",
                json={"quizCategoryId": "cat-1", "url": "file:///tmp/questions.csv"},
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "僅接受公開 HTTP/HTTPS 連結")
        resolver.assert_not_called()

    def test_import_url_is_row_tolerant_and_invalidates_review_after_insert(self):
        class Response:
            headers = {"Content-Type": "text/csv; charset=utf-8"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            @staticmethod
            def read(_limit):
                return (
                    "question,optionA,optionB,correct\n"
                    "有效題,A,B,B\n"
                    ",只有一個選項,,A\n"
                ).encode("utf-8")

        with patch(
            "teacher_app.assessments.runtime_question_routes.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
        ), patch(
            "teacher_app.assessments.runtime_question_routes.urllib.request.urlopen",
            return_value=Response(),
        ):
            response = self.client.post(
                "/api/quiz-questions/import-url",
                json={"quizCategoryId": "cat-1", "url": "https://example.test/questions.csv"},
            )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertEqual(payload["imported"], 1)
        self.assertEqual(payload["errors"], ["第2題格式不足"])
        self.assertTrue(payload["reviewInvalidated"])
        conn, _ = self.base.connect()
        try:
            category = conn.execute(
                "SELECT review_status,active FROM quiz_categories WHERE id='cat-1'"
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(category["review_status"], "draft")
        self.assertEqual(category["active"], 0)

    def _assert_repository_template_imports_cleanly(self, filename, content_type):
        body = ROOT.joinpath(filename).read_bytes()

        class Response:
            headers = {"Content-Type": content_type}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            @staticmethod
            def read(_limit):
                return body

        with patch(
            "teacher_app.assessments.runtime_question_routes.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
        ), patch(
            "teacher_app.assessments.runtime_question_routes.urllib.request.urlopen",
            return_value=Response(),
        ):
            response = self.client.post(
                "/api/quiz-questions/import-url",
                json={"quizCategoryId": "cat-1", "url": f"https://example.test/{filename}"},
            )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertEqual(payload["imported"], 4)
        self.assertEqual(payload["errors"], [])
        self.assertTrue(payload["reviewInvalidated"])

    def test_repository_csv_import_template_matches_current_validator(self):
        self._assert_repository_template_imports_cleanly(
            "QUESTION_IMPORT_TEMPLATE.csv",
            "text/csv; charset=utf-8",
        )

    def test_repository_json_import_template_matches_current_validator(self):
        self._assert_repository_template_imports_cleanly(
            "QUESTION_IMPORT_TEMPLATE.json",
            "application/json; charset=utf-8",
        )

    def test_import_url_csv_true_false_alias_and_chinese_answer_are_canonicalized(self):
        body = (
            "question,questionType,correct,tag\n"
            "收到檢體後可以略過病人身分核對。,是非題,否,檢體處理\n"
        ).encode("utf-8")

        class Response:
            headers = {"Content-Type": "text/csv; charset=utf-8"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            @staticmethod
            def read(_limit):
                return body

        with patch(
            "teacher_app.assessments.runtime_question_routes.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
        ), patch(
            "teacher_app.assessments.runtime_question_routes.urllib.request.urlopen",
            return_value=Response(),
        ):
            response = self.client.post(
                "/api/quiz-questions/import-url",
                json={"quizCategoryId": "cat-1", "url": "https://example.test/questions.csv"},
            )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(response.get_json()["imported"], 1)
        self.assertEqual(response.get_json()["errors"], [])
        conn, _ = self.base.connect()
        try:
            true_false = conn.execute(
                "SELECT question_type,options,correct FROM quiz_questions WHERE question LIKE '收到檢體後%'"
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(true_false["question_type"], "true_false")
        self.assertEqual(true_false["options"], '["是", "否"]')
        self.assertEqual(true_false["correct"], 1)

    def test_import_url_rejects_malformed_and_out_of_range_correct_values(self):
        body = (
            '[{"question":"格式錯誤","questionType":"choice","options":["A","B"],"correct":"Z"},'
            '{"question":"超出範圍","questionType":"choice","options":["A","B"],"correct":9},'
            '{"question":"有效題","questionType":"choice","options":["A","B"],"correct":"B"}]'
        ).encode("utf-8")

        class Response:
            headers = {"Content-Type": "application/json"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            @staticmethod
            def read(_limit):
                return body

        with patch(
            "teacher_app.assessments.runtime_question_routes.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
        ), patch(
            "teacher_app.assessments.runtime_question_routes.urllib.request.urlopen",
            return_value=Response(),
        ):
            response = self.client.post(
                "/api/quiz-questions/import-url",
                json={"quizCategoryId": "cat-1", "url": "https://example.test/questions.json"},
            )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertEqual(payload["imported"], 1)
        self.assertEqual(
            payload["errors"],
            ["第1題：正確答案格式錯誤", "第2題：正確答案超出選項範圍"],
        )
        conn, _ = self.base.connect()
        try:
            row = conn.execute(
                "SELECT question,correct FROM quiz_questions WHERE question='有效題'"
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(row["correct"], 1)

    def test_import_url_required_fields_report_exact_row_errors_without_review_invalidation(self):
        body = (
            '[{"question":"","questionType":"choice","options":["A","B"],"correct":0},'
            '{"question":"複選缺答案","questionType":"multi","options":["A","B"]},'
            '{"question":"填空缺答案","questionType":"fill"}]'
        ).encode("utf-8")

        class Response:
            headers = {"Content-Type": "application/json"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            @staticmethod
            def read(_limit):
                return body

        with patch(
            "teacher_app.assessments.runtime_question_routes.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
        ), patch(
            "teacher_app.assessments.runtime_question_routes.urllib.request.urlopen",
            return_value=Response(),
        ):
            response = self.client.post(
                "/api/quiz-questions/import-url",
                json={"quizCategoryId": "cat-1", "url": "https://example.test/questions.json"},
            )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(
            response.get_json(),
            {
                "ok": True,
                "imported": 0,
                "errors": [
                    "第1題格式不足",
                    "第2題缺少多選正確答案",
                    "第3題缺少填空可接受答案",
                ],
                "reviewInvalidated": False,
            },
        )
        conn, _ = self.base.connect()
        try:
            category = conn.execute(
                "SELECT review_status,active FROM quiz_categories WHERE id='cat-1'"
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(category["review_status"], "approved")
        self.assertEqual(category["active"], 1)

    def test_import_url_malformed_json_structure_preserves_stable_error(self):
        body = b'{"questions":{"question":"not-an-array"}}'

        class Response:
            headers = {"Content-Type": "application/json"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            @staticmethod
            def read(_limit):
                return body

        with patch(
            "teacher_app.assessments.runtime_question_routes.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
        ), patch(
            "teacher_app.assessments.runtime_question_routes.urllib.request.urlopen",
            return_value=Response(),
        ):
            response = self.client.post(
                "/api/quiz-questions/import-url",
                json={"quizCategoryId": "cat-1", "url": "https://example.test/questions.json"},
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json(),
            {"error": "JSON 格式需為題目陣列，或使用 questions 陣列"},
        )

    def test_import_url_object_without_questions_is_an_empty_import(self):
        body = b'{"metadata":{"title":"empty export"}}'

        class Response:
            headers = {"Content-Type": "application/json"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            @staticmethod
            def read(_limit):
                return body

        with patch(
            "teacher_app.assessments.runtime_question_routes.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
        ), patch(
            "teacher_app.assessments.runtime_question_routes.urllib.request.urlopen",
            return_value=Response(),
        ):
            response = self.client.post(
                "/api/quiz-questions/import-url",
                json={"quizCategoryId": "cat-1", "url": "https://example.test/questions.json"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {"ok": True, "imported": 0, "errors": [], "reviewInvalidated": False},
        )

    def test_import_url_duplicate_rows_are_additive_and_unknown_type_falls_back_to_choice(self):
        body = (
            '[{"question":"重複題","questionType":"unsupported","options":["A","B"],"correct":"A"},'
            '{"question":"重複題","questionType":"unsupported","options":["A","B"],"correct":"A"}]'
        ).encode("utf-8")

        class Response:
            headers = {"Content-Type": "application/json"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            @staticmethod
            def read(_limit):
                return body

        with patch(
            "teacher_app.assessments.runtime_question_routes.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
        ), patch(
            "teacher_app.assessments.runtime_question_routes.urllib.request.urlopen",
            return_value=Response(),
        ):
            response = self.client.post(
                "/api/quiz-questions/import-url",
                json={"quizCategoryId": "cat-1", "url": "https://example.test/questions.json"},
            )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(response.get_json()["imported"], 2)
        self.assertEqual(response.get_json()["errors"], [])
        conn, _ = self.base.connect()
        try:
            rows = conn.execute(
                "SELECT question_type FROM quiz_questions WHERE question='重複題' ORDER BY sort_order"
            ).fetchall()
        finally:
            conn.close()
        self.assertEqual([row["question_type"] for row in rows], ["choice", "choice"])

    def test_ai_import_rejects_malformed_bulk_semantics_without_partial_write(self):
        cases = (
            (
                {"question": "bad options", "questionType": "choice", "options": "AB", "correct": 0},
                "批次匯入失敗：選項格式錯誤",
            ),
            (
                {"question": "bad correct", "questionType": "choice", "options": ["A", "B"], "correct": 9},
                "批次匯入失敗：正確答案超出選項範圍",
            ),
            (
                {
                    "question": "bad multi",
                    "questionType": "multi",
                    "options": ["A", "B"],
                    "answerConfig": {"correctIndices": [0, 9]},
                },
                "批次匯入失敗：多選題正確選項超出選項範圍",
            ),
            (
                {
                    "question": "bad fill",
                    "questionType": "fill",
                    "answerConfig": {"acceptedAnswers": "RBC"},
                },
                "批次匯入失敗：填空題可接受答案格式錯誤",
            ),
        )
        for invalid, expected_error in cases:
            with self.subTest(expected_error=expected_error):
                response = self.client.post(
                    "/api/ai-questions/import",
                    json={
                        "quizCategoryId": "cat-1",
                        "questions": [
                            invalid,
                            {"question": "should-not-write", "questionType": "choice", "options": ["A", "B"], "correct": 0},
                        ],
                    },
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.get_json(), {"error": expected_error})
                conn, _ = self.base.connect()
                try:
                    count = conn.execute(
                        "SELECT COUNT(*) AS n FROM quiz_questions WHERE question='should-not-write'"
                    ).fetchone()["n"]
                finally:
                    conn.close()
                self.assertEqual(count, 0)

    def test_ai_import_true_false_and_non_object_row_contract(self):
        response = self.client.post(
            "/api/ai-questions/import",
            json={
                "quizCategoryId": "cat-1",
                "questions": [
                    "bad-row",
                    {"question": "是非候選題", "questionType": "true_false", "correct": 1},
                ],
            },
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertEqual(payload["imported"], 1)
        self.assertEqual(payload["errors"], ["第1題：題目格式錯誤"])
        self.assertEqual(payload["questions"][0]["options"], ["是", "否"])
        self.assertEqual(payload["questions"][0]["correct"], 1)

    def test_ai_import_empty_selection_preserves_stable_error(self):
        response = self.client.post(
            "/api/ai-questions/import",
            json={"quizCategoryId": "cat-1", "questions": []},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "請至少勾選一題"})

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

    def test_batch_delete_rejects_missing_question_ids_atomically(self):
        self.base.user = {"username": "root", "role": "system_admin"}
        response = self.client.post(
            "/api/quiz-questions/batch-delete",
            json={"ids": ["q-seed", "q-missing"]},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["missing"], ["q-missing"])
        conn, _ = self.base.connect()
        try:
            remaining = conn.execute(
                "SELECT COUNT(*) AS n FROM quiz_questions WHERE id='q-seed'"
            ).fetchone()["n"]
        finally:
            conn.close()
        self.assertEqual(remaining, 1)

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
                json={"quizCategoryId": "cat-direct", "materialIds": ["mat-direct"]},
            )
            self.assertEqual(generated.status_code, 202, generated.get_data(as_text=True))
            job_id = generated.get_json()["jobId"]
            self.assertEqual(len(generated_calls), 0)
            processor = ai_jobs.AiQuestionJobProcessor(runtime)
            self.assertTrue(processor.run_job(job_id))
        completed = client.get(f"/api/ai-questions/jobs/{job_id}")
        self.assertEqual(completed.status_code, 200, completed.get_data(as_text=True))
        self.assertEqual(completed.get_json()["status"], "completed")
        self.assertEqual(len(generated_calls), 1)

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
                json={"quizCategoryId": "cat-direct", "materialIds": ["mat-direct"]},
            )
            self.assertEqual(failed.status_code, 202)
            failed_job_id = failed.get_json()["jobId"]
            self.assertTrue(processor.run_job(failed_job_id))
        failed_state = client.get(f"/api/ai-questions/jobs/{failed_job_id}")
        self.assertEqual(failed_state.status_code, 200)
        self.assertEqual(failed_state.get_json()["status"], "failed")
        self.assertEqual(failed_state.get_json()["error"], "generation failed")
        self.assertEqual(failed_state.get_json()["progress"]["stage"], "AI 出題失敗")

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
