"""Whisper 第一次使用時，不能被 Kokoro 自動開啟的 HF 離線模式擋住（2026-10-13）。"""
import os
import unittest
from unittest import mock

from teacher_app.materials import media_audio_runtime, media_subtitle_runtime


class _Local:
    whisper_model = "small"
    whisper_device = "cpu"
    whisper_compute_type = "int8"


class WhisperOfflineRetryTests(unittest.TestCase):
    def tearDown(self):
        media_audio_runtime._HF_OFFLINE_AUTO = False
        os.environ.pop("HF_HUB_OFFLINE", None)

    def test_retries_once_after_lifting_automatic_offline_mode(self):
        media_audio_runtime._HF_OFFLINE_AUTO = True
        os.environ["HF_HUB_OFFLINE"] = "1"
        calls = []

        def model_cls(*args, **kwargs):
            calls.append(os.environ.get("HF_HUB_OFFLINE"))
            if os.environ.get("HF_HUB_OFFLINE") == "1":
                raise RuntimeError("Cannot find an appropriate cached snapshot folder")
            return "model"

        self.assertEqual(media_subtitle_runtime._load_whisper_model(model_cls, _Local()), "model")
        self.assertEqual(calls, ["1", None])
        self.assertEqual(os.environ.get("HF_HUB_OFFLINE"), "1")

    def test_explicit_offline_flag_is_lifted_only_for_the_download_then_restored(self):
        media_audio_runtime._HF_OFFLINE_AUTO = False
        os.environ["HF_HUB_OFFLINE"] = "1"

        def model_cls(*args, **kwargs):
            if os.environ.get("HF_HUB_OFFLINE") == "1":
                raise RuntimeError("Cannot find an appropriate cached snapshot folder")
            return "model"

        self.assertEqual(media_subtitle_runtime._load_whisper_model(model_cls, _Local()), "model")
        self.assertEqual(os.environ.get("HF_HUB_OFFLINE"), "1")

    def test_download_can_be_forbidden_by_the_operator(self):
        os.environ["HF_HUB_OFFLINE"] = "1"

        def model_cls(*args, **kwargs):
            raise RuntimeError("Cannot find an appropriate cached snapshot folder")

        with mock.patch.dict(os.environ, {"LOCAL_WHISPER_ALLOW_MODEL_DOWNLOAD": "0"}):
            with self.assertRaises(RuntimeError):
                media_subtitle_runtime._load_whisper_model(model_cls, _Local())

    def test_error_is_not_masked_when_offline_mode_is_not_the_cause(self):
        os.environ.pop("HF_HUB_OFFLINE", None)

        def model_cls(*args, **kwargs):
            raise RuntimeError("some other failure")

        with self.assertRaises(RuntimeError):
            media_subtitle_runtime._load_whisper_model(model_cls, _Local())

    def test_cached_model_loads_without_touching_offline_mode(self):
        media_audio_runtime._HF_OFFLINE_AUTO = True
        os.environ["HF_HUB_OFFLINE"] = "1"
        self.assertEqual(media_subtitle_runtime._load_whisper_model(lambda *a, **k: "ok", _Local()), "ok")
        self.assertEqual(os.environ.get("HF_HUB_OFFLINE"), "1")


if __name__ == "__main__":
    unittest.main()
