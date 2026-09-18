import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from teacher_app.assessments import ai_runtime
from teacher_app.assessments.question_runtime import build_canonical_question_runtime
from teacher_app.common import privacy


def _settings(**overrides):
    values = dict(
        provider="groq",
        groq_api_key="groq-key",
        groq_model="groq-model",
        groq_transcribe_model="whisper-model",
        gemini_api_key="gemini-key",
        gemini_model="gemini-model",
        openai_api_key="openai-key",
        openai_model="openai-model",
        source_max_chars=50000,
        max_questions=15,
        media_max_mb=300,
        max_materials=4,
        video_frame_count=3,
        free_only_mode=True,
    )
    values.update(overrides)
    return ai_runtime.AISettings(**values)


class _Response:
    def __init__(self, payload, status=200, text=""):
        self._payload = payload
        self.status_code = status
        self.text = text

    def json(self):
        return self._payload


class AIRuntimeProviderTests(unittest.TestCase):
    def test_env_defaults_and_provider_selection_match_legacy(self):
        with patch.dict("os.environ", {}, clear=True):
            settings = ai_runtime.ai_settings()
        self.assertEqual(settings.provider, "groq")
        self.assertEqual(settings.groq_model, "qwen/qwen3.6-27b")
        self.assertEqual(settings.groq_transcribe_model, "whisper-large-v3-turbo")
        self.assertEqual(settings.gemini_model, "gemini-3.8-flash")
        self.assertEqual(settings.openai_model, "gpt-5.6-luna")
        self.assertEqual(settings.source_max_chars, 50000)
        self.assertEqual(settings.max_questions, 15)
        self.assertEqual(settings.media_max_mb, 300)
        self.assertEqual(settings.max_materials, 4)
        self.assertEqual(settings.video_frame_count, 3)
        self.assertTrue(settings.free_only_mode)

        self.assertEqual(ai_runtime.active_ai_provider(_settings(provider="auto", free_only_mode=True)), "groq")
        self.assertEqual(ai_runtime.active_ai_provider(_settings(provider="openai", free_only_mode=True)), "openai")
        self.assertEqual(
            ai_runtime.active_ai_provider(
                _settings(provider="auto", free_only_mode=False, groq_api_key="", gemini_api_key="", openai_api_key="openai")
            ),
            "openai",
        )
        self.assertEqual(ai_runtime.active_ai_provider(_settings(provider="bogus")), "groq")

    def test_configured_and_model_follow_active_provider_and_optional_google_client(self):
        groq = _settings(provider="groq", groq_api_key="g")
        self.assertTrue(ai_runtime.ai_question_is_configured(groq))
        self.assertEqual(ai_runtime.ai_model_name(groq), "groq-model")

        openai = _settings(provider="openai", openai_api_key="o")
        self.assertTrue(ai_runtime.ai_question_is_configured(openai))
        self.assertEqual(ai_runtime.ai_model_name(openai), "openai-model")

        gemini = _settings(provider="gemini", gemini_api_key="g")
        with patch.object(ai_runtime, "google_genai", None):
            self.assertFalse(ai_runtime.ai_question_is_configured(gemini))
        with patch.object(ai_runtime, "google_genai", object()):
            self.assertTrue(ai_runtime.ai_question_is_configured(gemini))
        self.assertEqual(ai_runtime.ai_model_name(gemini), "gemini-model")

    def test_infer_strategy_preserves_legacy_priority(self):
        self.assertEqual(ai_runtime.infer_ai_strategy([{"title": "血球圖譜 QC 安全"}]), "recognition")
        self.assertEqual(ai_runtime.infer_ai_strategy([{"title": "SOP 故障排除"}]), "regulation")
        self.assertEqual(ai_runtime.infer_ai_strategy([{"title": "異常案例"}]), "scenario")
        self.assertEqual(ai_runtime.infer_ai_strategy([{"title": "QC 品質"}]), "safety")
        self.assertEqual(ai_runtime.infer_ai_strategy([{"filename": "demo.mp4"}]), "workflow")
        self.assertEqual(ai_runtime.infer_ai_strategy([{"title": "一般教材"}]), "balanced")

    def test_public_privacy_target_is_explicit_and_wrappable(self):
        self.assertEqual(
            ai_runtime.EXTERNAL_AI_TEXT_EXTRACTOR_TARGETS,
            ("extract_material_text_for_ai", "groq_transcribe"),
        )
        original = ai_runtime.extract_material_text_for_ai
        self.addCleanup(setattr, ai_runtime, "extract_material_text_for_ai", original)

        def extractor(_entry, **_kwargs):
            return "姓名：王小明 病歷號：ABC12345", 25

        privacy.wrap_text_extractor(ai_runtime, "extract_material_text_for_ai", extractor)
        masked, total = ai_runtime.extract_material_text_for_ai({})
        self.assertIn("[已遮罩]", masked)
        self.assertEqual(total, 25)

    def test_explicit_privacy_targets_include_transcription_output(self):
        original_extract = ai_runtime.extract_material_text_for_ai
        original_transcribe = ai_runtime.groq_transcribe
        self.addCleanup(setattr, ai_runtime, "extract_material_text_for_ai", original_extract)
        self.addCleanup(setattr, ai_runtime, "groq_transcribe", original_transcribe)
        privacy.install_extractor_wrappers(
            ai_runtime,
            ai_runtime.EXTERNAL_AI_TEXT_EXTRACTOR_TARGETS,
        )
        self.assertTrue(getattr(ai_runtime.extract_material_text_for_ai, "_teacher64_deid", False))
        self.assertTrue(getattr(ai_runtime.groq_transcribe, "_teacher64_deid", False))

        with tempfile.TemporaryDirectory() as temp:
            audio = Path(temp) / "audio.mp3"
            audio.write_bytes(b"audio")
            response = _Response({"text": "病歷號：ABC12345"})
            with patch.object(ai_runtime.requests, "post", return_value=response):
                transcript = ai_runtime.groq_transcribe(audio, settings=_settings())
        self.assertEqual(transcript, "病歷號：[已遮罩]")


class AIRuntimeSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.paths = SimpleNamespace(
            tmp_dir=root / "tmp",
            upload_dir=root / "uploads",
            question_images_dir=root / "question-images",
            upload_progress_dir=root / "progress",
        )
        self.paths.tmp_dir.mkdir(parents=True)
        self.paths.upload_dir.mkdir(parents=True)
        self.paths.question_images_dir.mkdir(parents=True)
        self.paths.upload_progress_dir.mkdir(parents=True)

    def test_local_material_source_and_text_extraction_use_canonical_classification(self):
        directory = self.paths.upload_dir / "mat-1"
        directory.mkdir(parents=True)
        source = directory / "source.txt"
        source.write_text("教材文字 " * 30, encoding="utf-8")
        entry = {
            "id": "mat-1",
            "filename": "notes.txt",
            "storageFilename": "source.txt",
            "storageBackend": "local",
        }
        text, total = ai_runtime.extract_material_text_for_ai(
            entry,
            settings=_settings(source_max_chars=100),
            paths_provider=lambda: self.paths,
        )
        self.assertEqual(len(text), 100)
        self.assertGreater(total, len(text))
        self.assertEqual(list(self.paths.tmp_dir.iterdir()), [])

    def test_source_storage_errors_keep_chinese_contracts(self):
        for backend, message in (
            ("mega", "此教材缺少 MEGA 原始檔 ID。"),
            ("gdrive", "此教材缺少 Google Drive 原始檔 ID。"),
        ):
            with self.subTest(backend=backend):
                with self.assertRaisesRegex(RuntimeError, message):
                    ai_runtime.material_source_to_temp(
                        {"id": "m", "filename": "a.pdf", "storageBackend": backend},
                        paths_provider=lambda: self.paths,
                    )

        with patch.object(ai_runtime.providers, "r2_is_configured", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "此教材位於 R2，但目前伺服器未設定 R2 金鑰"):
                ai_runtime.material_source_to_temp(
                    {"id": "m", "filename": "a.pdf", "storageBackend": "r2", "storageKey": "key"},
                    paths_provider=lambda: self.paths,
                )

    def test_text_extraction_rejects_builtin_short_and_unsupported_sources(self):
        with self.assertRaisesRegex(RuntimeError, "內建舊教材沒有保留原始"):
            ai_runtime.extract_material_text_for_ai({"isBuiltin": True})

        directory = self.paths.upload_dir / "short"
        directory.mkdir(parents=True)
        (directory / "source.txt").write_text("短文字", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "教材可擷取的文字太少"):
            ai_runtime.extract_material_text_for_ai(
                {"id": "short", "filename": "short.txt", "storageFilename": "source.txt"},
                paths_provider=lambda: self.paths,
            )

        directory = self.paths.upload_dir / "zip"
        directory.mkdir(parents=True)
        (directory / "source.zip").write_bytes(b"zip")
        with self.assertRaisesRegex(RuntimeError, "目前文字擷取支援"):
            ai_runtime.extract_material_text_for_ai(
                {"id": "zip", "filename": "source.zip", "storageFilename": "source.zip"},
                paths_provider=lambda: self.paths,
            )

    def test_deidentified_material_text_reaches_external_generation_payload(self):
        directory = self.paths.upload_dir / "privacy"
        directory.mkdir(parents=True)
        source = directory / "source.txt"
        source.write_text(("教材 A123456789 檢驗流程。" * 20), encoding="utf-8")
        entry = {
            "id": "privacy",
            "filename": "source.txt",
            "storageFilename": "source.txt",
            "storageBackend": "local",
            "title": "姓名：王小明 教材",
        }
        response = _Response({
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "questions": [{
                            "questionType": "choice",
                            "question": "題目",
                            "options": ["A", "B", "C", "D"],
                            "correct": 0,
                        }]
                    }, ensure_ascii=False)
                }
            }]
        })
        original_extract = ai_runtime.extract_material_text_for_ai
        original_transcribe = ai_runtime.groq_transcribe
        self.addCleanup(setattr, ai_runtime, "extract_material_text_for_ai", original_extract)
        self.addCleanup(setattr, ai_runtime, "groq_transcribe", original_transcribe)
        privacy.install_extractor_wrappers(
            ai_runtime,
            ai_runtime.EXTERNAL_AI_TEXT_EXTRACTOR_TARGETS,
        )
        with patch.dict("os.environ", {"AI_EXTERNAL_MEDIA_ALLOWED": "false"}), patch.object(
            ai_runtime, "extract_document_preview_frames", return_value=[]
        ) as previews, patch.object(ai_runtime.requests, "post", return_value=response) as post:
            ai_runtime.generate_groq_multisource_candidates(
                [entry],
                count=1,
                qtype="choice",
                difficulty="standard",
                focus="電話：0912345678",
                source_title="病歷號：ABC12345",
                existing_questions=["舊題 A223456789"],
                settings=_settings(provider="groq"),
                paths_provider=lambda: self.paths,
            )
        prompt = post.call_args.kwargs["json"]["messages"][0]["content"][0]["text"]
        self.assertNotIn("A123456789", prompt)
        self.assertNotIn("王小明", prompt)
        self.assertNotIn("ABC12345", prompt)
        self.assertNotIn("0912345678", prompt)
        self.assertNotIn("A223456789", prompt)
        self.assertIn("[身分證號已遮罩]", prompt)
        previews.assert_not_called()
        self.assertFalse(any(item.get("type") == "image_url" for item in post.call_args.kwargs["json"]["messages"][0]["content"]))


class AIRuntimeGenerationTests(unittest.TestCase):
    def test_groq_text_generation_preserves_payload_timeout_and_normalization(self):
        response = _Response({
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "questions": [{
                            "questionType": "multi",
                            "question": "何者正確？",
                            "options": ["A", "B", "C", "D"],
                            "correct": 0,
                            "answerConfig": {"correctIndices": [0, 2]},
                            "sourceHint": "第1頁",
                        }]
                    }, ensure_ascii=False)
                }
            }]
        })
        with patch.object(ai_runtime.requests, "post", return_value=response) as post:
            questions = ai_runtime.generate_ai_question_candidates(
                "教材內容 " * 30,
                count=1,
                qtype="multi",
                difficulty="standard",
                focus="",
                source_title="教材",
                settings=_settings(provider="groq"),
            )
        self.assertEqual(questions[0]["questionType"], "multi")
        self.assertEqual(questions[0]["answerConfig"]["correctIndices"], [0, 2])
        self.assertEqual(post.call_args.args[0], "https://api.groq.com/openai/v1/chat/completions")
        self.assertEqual(post.call_args.kwargs["timeout"], 120)
        self.assertEqual(post.call_args.kwargs["json"]["model"], "groq-model")

    def test_groq_free_limit_error_contract_is_preserved(self):
        with patch.object(ai_runtime.requests, "post", return_value=_Response({}, status=429)):
            with self.assertRaisesRegex(RuntimeError, "Groq 免費 AI 額度已達上限，請稍後再試"):
                ai_runtime.generate_ai_question_candidates(
                    "教材文字 " * 30,
                    count=1,
                    qtype="choice",
                    difficulty="standard",
                    focus="",
                    source_title="教材",
                    settings=_settings(provider="groq"),
                )

    def test_groq_multisource_preserves_progress_stages_and_text_source_flow(self):
        response = _Response({
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "questions": [{
                            "questionType": "choice",
                            "question": "題目",
                            "options": ["A", "B", "C", "D"],
                            "correct": 0,
                        }]
                    }, ensure_ascii=False)
                }
            }]
        })
        progress = []
        with patch.object(
            ai_runtime,
            "extract_material_text_for_ai",
            return_value=("教材文字 " * 30, 150),
        ), patch.object(
            ai_runtime,
            "material_source_to_temp",
            side_effect=RuntimeError("preview unavailable"),
        ), patch.object(ai_runtime.requests, "post", return_value=response) as post:
            questions = ai_runtime.generate_groq_multisource_candidates(
                [{"id": "m1", "filename": "notes.txt", "title": "教材"}],
                count=1,
                qtype="choice",
                difficulty="standard",
                focus="",
                source_title="教材",
                strategy="auto",
                existing_questions=["舊題"],
                progress_id="p1",
                progress_callback=lambda *args, **kwargs: progress.append((args, kwargs)),
                settings=_settings(provider="groq"),
            )
        self.assertEqual(len(questions), 1)
        stages = [item[0][2] for item in progress]
        self.assertIn("準備 AI 教材", stages)
        self.assertIn("解析文件內容", stages)
        self.assertIn("AI 正在產生候選題", stages)
        self.assertIn("檢查 AI 題目格式", stages)
        self.assertIn("整理候選題", stages)
        self.assertEqual(post.call_args.kwargs["timeout"], 180)
        prompt = post.call_args.kwargs["json"]["messages"][0]["content"][0]["text"]
        self.assertIn("教材文字", prompt)
        self.assertIn("舊題", prompt)

    def test_openai_generation_preserves_responses_api_and_error_contract(self):
        payload = {
            "output": [{
                "content": [{
                    "type": "output_text",
                    "text": json.dumps({
                        "questions": [{
                            "questionType": "choice",
                            "question": "題目",
                            "options": ["A", "B", "C", "D"],
                            "correct": 1,
                            "tag": "AI",
                            "explanation": "詳解",
                            "sourceHint": "第1頁",
                        }]
                    }, ensure_ascii=False),
                }]
            }]
        }
        with patch.object(ai_runtime.requests, "post", return_value=_Response(payload)) as post:
            questions = ai_runtime.generate_openai_question_candidates(
                "教材文字 A123456789",
                count=1,
                qtype="choice",
                difficulty="basic",
                focus="電話：0912345678",
                source_title="病歷號：ABC12345",
                settings=_settings(provider="openai"),
            )
        self.assertEqual(questions[0]["correct"], 1)
        self.assertEqual(post.call_args.args[0], "https://api.openai.com/v1/responses")
        self.assertEqual(post.call_args.kwargs["timeout"], 120)
        self.assertEqual(post.call_args.kwargs["json"]["model"], "openai-model")
        self.assertEqual(post.call_args.kwargs["json"]["reasoning"], {"effort": "low"})
        outbound = post.call_args.kwargs["json"]["input"][1]["content"]
        self.assertNotIn("A123456789", outbound)
        self.assertNotIn("0912345678", outbound)
        self.assertNotIn("ABC12345", outbound)

        with patch.object(
            ai_runtime.requests,
            "post",
            return_value=_Response({"error": {"message": "bad key"}}, status=401),
        ):
            with self.assertRaisesRegex(RuntimeError, "AI 服務回傳 HTTP 401：bad key"):
                ai_runtime.generate_openai_question_candidates(
                    "教材文字",
                    count=1,
                    qtype="choice",
                    difficulty="basic",
                    focus="",
                    source_title="教材",
                    settings=_settings(provider="openai"),
                )

    def test_gemini_text_generation_uses_optional_client_and_deletes_upload_only_when_used(self):
        fake_client = Mock()
        fake_client.models.generate_content.return_value = SimpleNamespace(
            text=json.dumps({
                "questions": [{
                    "questionType": "fill",
                    "question": "填空",
                    "options": [],
                    "answerConfig": {"acceptedAnswers": ["答案"]},
                }]
            }, ensure_ascii=False)
        )
        fake_genai = SimpleNamespace(Client=Mock(return_value=fake_client))
        fake_types = SimpleNamespace(GenerateContentConfig=lambda **kwargs: kwargs)
        with patch.object(ai_runtime, "google_genai", fake_genai), patch.object(ai_runtime, "google_genai_types", fake_types):
            questions = ai_runtime.generate_gemini_question_candidates(
                source_text="教材文字",
                count=1,
                qtype="fill",
                difficulty="standard",
                focus="",
                source_title="教材",
                settings=_settings(provider="gemini"),
            )
        self.assertEqual(questions[0]["questionType"], "fill")
        self.assertEqual(questions[0]["answerConfig"]["acceptedAnswers"], ["答案"])
        fake_genai.Client.assert_called_once_with(api_key="gemini-key")
        self.assertEqual(fake_client.models.generate_content.call_args.kwargs["model"], "gemini-model")
        fake_client.files.delete.assert_not_called()

    def test_multisource_orchestration_reads_existing_questions_and_reports_progress(self):
        settings = _settings(provider="groq")
        entries = [{"id": "m1", "filename": "notes.txt", "title": "教材"}]
        progress = []
        candidate = [{"questionType": "choice", "question": "新題", "options": ["A", "B", "C", "D"], "correct": 0}]
        with patch.object(
            ai_runtime.assessment_repository,
            "list_questions",
            return_value=[{"question": "舊題"}],
        ) as listed, patch.object(
            ai_runtime,
            "generate_groq_multisource_candidates",
            return_value=candidate,
        ) as generate:
            result, title, kinds = ai_runtime.generate_ai_questions_from_materials(
                entries,
                category_id="cat-1",
                count=3,
                qtype="mixed_all",
                difficulty="standard",
                focus="重點",
                strategy="auto",
                progress_id="p1",
                progress_callback=lambda *args, **kwargs: progress.append((args, kwargs)),
                settings=settings,
            )
        self.assertEqual(result, candidate)
        self.assertEqual(title, "教材")
        self.assertEqual(kinds, ["text"])
        listed.assert_called_once_with("cat-1", include_inactive=True)
        self.assertEqual(progress[0][0][:3], ("p1", 6, "讀取正式題庫"))
        self.assertEqual(generate.call_args.kwargs["existing_questions"], ["舊題"])
        self.assertEqual(generate.call_args.kwargs["strategy"], "auto")

    def test_multisource_limits_and_openai_backup_contracts(self):
        settings = _settings(provider="gemini", max_materials=1)
        with self.assertRaisesRegex(RuntimeError, "一次最多可選 1 份教材"):
            with patch.object(ai_runtime, "google_genai", object()), patch.object(ai_runtime, "google_genai_types", object()):
                ai_runtime.generate_gemini_multisource_candidates(
                    [{"id": "a"}, {"id": "b"}],
                    count=1,
                    qtype="choice",
                    difficulty="standard",
                    focus="",
                    source_title="教材",
                    settings=settings,
                )

        with self.assertRaisesRegex(RuntimeError, "影片互動題需要至少選擇 1 支影片教材"):
            with patch.object(ai_runtime.assessment_repository, "list_questions", return_value=[]):
                ai_runtime.generate_ai_questions_from_materials(
                    [{"id": "a", "filename": "a.txt"}],
                    category_id="cat",
                    count=1,
                    qtype="video_choice",
                    difficulty="standard",
                    focus="",
                    settings=_settings(provider="openai", free_only_mode=False),
                )

        with self.assertRaisesRegex(RuntimeError, "OpenAI 備援模式在此版本僅處理單一文字來源"):
            with patch.object(ai_runtime.assessment_repository, "list_questions", return_value=[]):
                ai_runtime.generate_ai_questions_from_materials(
                    [{"id": "a", "filename": "a.txt"}, {"id": "b", "filename": "b.txt"}],
                    category_id="cat",
                    count=1,
                    qtype="choice",
                    difficulty="standard",
                    focus="",
                    settings=_settings(provider="openai", free_only_mode=False),
                )


class CanonicalQuestionRuntimeBuilderTests(unittest.TestCase):
    def test_builder_uses_canonical_ai_runtime_without_owner_callbacks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = SimpleNamespace(
                tmp_dir=root / "tmp",
                upload_dir=root / "uploads",
                question_images_dir=root / "question-images",
                upload_progress_dir=root / "progress",
            )
            for value in vars(paths).values():
                Path(value).mkdir(parents=True, exist_ok=True)

            class LocalStorage:
                @staticmethod
                def active_backend():
                    return "local"

            settings = _settings(provider="groq", max_questions=7, source_max_chars=12345, max_materials=3)
            with patch.object(ai_runtime, "ai_settings", return_value=settings), patch.object(
                ai_runtime,
                "generate_ai_questions_from_materials",
                return_value=([{"question": "題"}], "教材", ["text"]),
            ) as generate:
                runtime = build_canonical_question_runtime(
                    paths_provider=lambda: paths,
                    storage_adapter=LocalStorage(),
                )
                result = runtime.generate_ai_questions_from_materials(
                    [{"id": "m"}],
                    category_id="cat",
                    count=1,
                    qtype="choice",
                    difficulty="standard",
                    focus="",
                    progress_id="p1",
                )
            self.assertEqual(result[1], "教材")
            self.assertEqual(runtime.max_questions, 7)
            self.assertEqual(runtime.source_max_chars, 12345)
            self.assertEqual(runtime.max_materials, 3)
            self.assertEqual(runtime.active_ai_provider(), "groq")
            self.assertEqual(runtime.ai_model_name(), "groq-model")
            self.assertIs(generate.call_args.kwargs["settings"], settings)
            self.assertTrue(callable(generate.call_args.kwargs["progress_callback"]))

    def test_ai_runtime_does_not_own_storage_secrets_or_http_routes(self):
        source = Path(ai_runtime.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "legacy_host",
            "R2_SECRET_ACCESS_KEY",
            "OCI_SECRET_ACCESS_KEY",
            "GDRIVE_CLIENT_SECRET",
            "MEGA_PASSWORD",
            "@app.",
            "Flask(",
            "insert_runtime_question",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
