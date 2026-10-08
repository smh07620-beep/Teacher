import unittest
from types import SimpleNamespace
from unittest.mock import patch

from teacher_app.assessments import ai_runtime, free_ai_fallback


class FreeAIFallbackTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.dict("os.environ", {"AI_RATE_LIMIT_RETRY_SECONDS": "0"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _settings(self):
        return ai_runtime.AISettings(
            provider="groq",
            groq_api_key="g",
            groq_model="groq-model",
            groq_transcribe_model="whisper-model",
            gemini_api_key="gm",
            gemini_model="gemini-model",
            openai_api_key="",
            openai_model="openai-model",
            source_max_chars=50000,
            max_questions=15,
            media_max_mb=300,
            max_materials=4,
            video_frame_count=3,
            free_only_mode=True,
        )

    def _local(self, enabled=True, ollama=True):
        return free_ai_fallback.LocalFallbackSettings(
            enabled=enabled,
            ollama_enabled=ollama,
            ollama_base_url="http://127.0.0.1:11434",
            ollama_model="qwen3:4b",
            ollama_timeout_seconds=240,
            whisper_enabled=True,
            whisper_model="small",
            whisper_device="cpu",
            whisper_compute_type="int8",
        )

    def test_free_chain_is_groq_then_gemini_then_local(self):
        settings = self._settings()
        with patch.object(free_ai_fallback.ai_privacy, "external_enabled", return_value=True), \
             patch.object(free_ai_fallback.ai_runtime, "google_genai", object()), \
             patch.object(free_ai_fallback.ai_runtime, "google_genai_types", object()):
            chain = free_ai_fallback.provider_chain(
                "groq", settings=settings, local=self._local()
            )
        self.assertEqual(chain, ["groq", "gemini", "ollama"])

    def test_external_disabled_leaves_only_local_fallback(self):
        with patch.object(free_ai_fallback.ai_privacy, "external_enabled", return_value=False):
            chain = free_ai_fallback.provider_chain(
                "groq", settings=self._settings(), local=self._local()
            )
        self.assertEqual(chain, ["ollama"])

    def test_localized_quota_error_is_retryable(self):
        self.assertTrue(
            free_ai_fallback.is_retryable_provider_error(
                RuntimeError("Groq 免費 AI 額度/速率已達上限，請稍後再試。")
            )
        )
        self.assertFalse(
            free_ai_fallback.is_retryable_provider_error(
                RuntimeError("AI 回傳的題目未通過格式檢查，請重新產生。")
            )
        )

    def test_quota_falls_back_but_validation_does_not(self):
        settings = self._settings()
        calls = []

        def groq():
            calls.append("groq")
            raise RuntimeError("Groq 免費 AI 額度已達上限，請稍後再試。")

        def gemini():
            calls.append("gemini")
            return "ok"

        with patch.object(
            free_ai_fallback,
            "provider_chain",
            return_value=["groq", "gemini", "ollama"],
        ):
            value, meta = free_ai_fallback.run_with_fallback(
                "groq",
                cloud_callers={"groq": groq, "gemini": gemini},
                local_caller=lambda: "local",
                settings=settings,
                local=self._local(),
            )
        self.assertEqual(value, "ok")
        self.assertEqual(calls, ["groq", "gemini"])
        self.assertEqual(meta["provider"], "gemini")
        self.assertTrue(meta["fallbackUsed"])

        calls.clear()

        def invalid():
            calls.append("groq")
            raise RuntimeError("AI 回傳的題目未通過格式檢查，請重新產生。")

        with patch.object(
            free_ai_fallback,
            "provider_chain",
            return_value=["groq", "gemini"],
        ):
            with self.assertRaisesRegex(RuntimeError, "格式檢查"):
                free_ai_fallback.run_with_fallback(
                    "groq",
                    cloud_callers={"groq": invalid, "gemini": gemini},
                    settings=settings,
                    local=self._local(),
                )
        self.assertEqual(calls, ["groq"])

    def test_provider_failures_are_logged_without_exception_message(self):
        settings = self._settings()

        def quota():
            raise RuntimeError("token=do-not-log 429 rate limit")

        with patch.object(
            free_ai_fallback,
            "provider_chain",
            return_value=["groq", "gemini"],
        ), patch.object(
            free_ai_fallback.LOGGER,
            "warning",
        ) as warning:
            value, meta = free_ai_fallback.run_with_fallback(
                "groq",
                cloud_callers={"groq": quota, "gemini": lambda: "ok"},
                settings=settings,
                local=self._local(),
            )

        self.assertEqual(value, "ok")
        self.assertEqual(meta["provider"], "gemini")
        rendered = "\n".join(str(call) for call in warning.call_args_list)
        self.assertIn("AI provider attempt failed", rendered)
        self.assertIn("groq", rendered)
        self.assertIn("gemini", rendered)
        self.assertIn("RuntimeError", rendered)
        self.assertNotIn("do-not-log", rendered)


    def test_worker_runtime_reports_actual_fallback_provider_and_model(self):
        settings = self._settings()
        original_calls = []
        gemini_calls = []

        def original_generate(entries, **kwargs):
            original_calls.append((entries, kwargs))
            raise RuntimeError("Groq 免費 AI 額度/速率已達上限，請稍後再試。")

        runtime = SimpleNamespace(
            generate_ai_questions_from_materials=original_generate,
            active_ai_provider=lambda: "groq",
            ai_model_name=lambda: "groq-model",
            paths_provider=lambda: None,
        )
        free_ai_fallback.install_question_runtime_fallback(runtime)

        with patch.object(free_ai_fallback.ai_runtime, "ai_settings", return_value=settings), \
             patch.object(free_ai_fallback, "provider_chain", return_value=["groq", "gemini"]), \
             patch.object(
                 free_ai_fallback.ai_runtime,
                 "generate_ai_questions_from_materials",
                 side_effect=lambda *args, **kwargs: (
                     gemini_calls.append(kwargs.get("settings").provider)
                     or ([{"question": "題"}], "教材", ["text"])
                 ),
             ):
            result = runtime.generate_ai_questions_from_materials(
                [{"id": "mat-1"}],
                category_id="quiz-1",
                count=1,
                qtype="choice",
                difficulty="standard",
                focus="",
                strategy="balanced",
            )
        self.assertEqual(result[0][0]["question"], "題")
        self.assertEqual(gemini_calls, ["gemini"])
        self.assertEqual(runtime.active_ai_provider(), "gemini")
        self.assertEqual(runtime.ai_model_name(), "gemini-model")
        self.assertEqual(len(original_calls), 1)

    def test_fallback_notice_names_the_reason(self):
        import requests
        self.assertIn("429", free_ai_fallback.describe_provider_error(RuntimeError("HTTP 429 RESOURCE_EXHAUSTED")))
        self.assertEqual(free_ai_fallback.describe_provider_error(requests.Timeout("x")), "連線逾時")
        self.assertIn("5xx", free_ai_fallback.describe_provider_error(RuntimeError("503 Service Unavailable")))
        seen = []

        def fail():
            raise RuntimeError("429 quota")

        with patch.object(free_ai_fallback, "provider_chain", return_value=["gemini", "ollama"]):
            free_ai_fallback.run_with_fallback(
                "gemini",
                cloud_callers={"gemini": fail},
                local_caller=lambda: "ok",
                settings=self._settings(),
                local=SimpleNamespace(enabled=True, ollama_model="m"),
                notify=lambda *args: seen.append(args),
            )
        self.assertEqual(seen, [("gemini", "ollama", "額度或速率限制（429）")])

    def test_rate_limit_is_retried_once_before_switching(self):
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("429 quota")
            return "ok"

        with patch.dict("os.environ", {"AI_RATE_LIMIT_RETRY_SECONDS": "1"}), \
                patch.object(free_ai_fallback.time, "sleep") as sleep, \
                patch.object(free_ai_fallback, "provider_chain", return_value=["groq", "ollama"]):
            value, meta = free_ai_fallback.run_with_fallback(
                "groq", cloud_callers={"groq": flaky}, local_caller=lambda: "local",
                settings=self._settings(), local=SimpleNamespace(enabled=True, ollama_model="m"),
            )
        self.assertEqual(value, "ok")
        self.assertEqual(meta["provider"], "groq")
        self.assertFalse(meta["fallbackUsed"])
        sleep.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
