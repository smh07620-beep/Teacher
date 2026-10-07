import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from teacher_app.materials import media_audio_runtime
from teacher_app.worker.libreoffice_warm import WarmLibreOfficeConverter


class FakeProcess:
    returncode = None

    def poll(self):
        return None

    def terminate(self):
        self.returncode = 0

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.returncode = -9


class LibreOfficeColdStartTests(unittest.TestCase):
    def _runtime(self, profile_root):
        return WarmLibreOfficeConverter("soffice", enabled=True, startup_timeout=1, profile_dir=profile_root)

    def test_warmup_does_a_real_conversion_and_marks_warmed(self):
        with tempfile.TemporaryDirectory() as temp_name:
            runtime = self._runtime(temp_name)
            converted = []

            def fake_run(command, **_kwargs):
                source = Path(command[-1])
                converted.append(source.name)
                self.assertIn("暖機", source.read_text(encoding="utf-8"))
                out_dir = Path(command[command.index("--outdir") + 1])
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / "warmup.pdf").write_bytes(b"%PDF-warmup")
                return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

            with patch("teacher_app.worker.libreoffice_warm.subprocess.Popen", return_value=FakeProcess()), patch(
                "teacher_app.worker.libreoffice_warm.subprocess.run", side_effect=fake_run
            ), patch("teacher_app.worker.libreoffice_warm.time.sleep"):
                self.assertTrue(runtime.warmup())
                status = runtime.status()
            self.assertEqual(converted, ["warmup.fodp"])
            self.assertTrue(status["warmed"])
            self.assertEqual(status["lastError"], "")
            runtime.close()
            # The profile stays warm on disk; only the resident process is gone.
            self.assertTrue(runtime.warmed)
            self.assertFalse(runtime.status()["armed"])

    def test_resident_instance_is_rearmed_after_every_conversion(self):
        with tempfile.TemporaryDirectory() as temp_name:
            runtime = self._runtime(temp_name)
            starts = []

            class Exiting(FakeProcess):
                def __init__(self):
                    starts.append(1)

                def poll(self):
                    return self.returncode

            def fake_run(command, **_kwargs):
                out_dir = Path(command[command.index("--outdir") + 1])
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / "x.pdf").write_bytes(b"%PDF")
                # LibreOffice quirk: the resident process exits after a forwarded job.
                runtime._process.returncode = 0
                return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

            with patch("teacher_app.worker.libreoffice_warm.subprocess.Popen", side_effect=lambda *a, **k: Exiting()), patch(
                "teacher_app.worker.libreoffice_warm.subprocess.run", side_effect=fake_run
            ), patch("teacher_app.worker.libreoffice_warm.time.sleep"):
                src = Path(temp_name) / "a.pptx"
                src.write_bytes(b"x")
                runtime.convert_to_pdf(src, Path(temp_name) / "o1", timeout=10)
                self.assertEqual(len(starts), 2)  # started for the job, re-armed after it
                runtime.convert_to_pdf(src, Path(temp_name) / "o2", timeout=10)
                self.assertEqual(len(starts), 3)
            runtime.close()

    def test_warmup_failure_never_raises_and_is_not_warmed(self):
        with tempfile.TemporaryDirectory() as temp_name:
            runtime = self._runtime(temp_name)
            with patch("teacher_app.worker.libreoffice_warm.subprocess.Popen", return_value=FakeProcess()), patch(
                "teacher_app.worker.libreoffice_warm.subprocess.run",
                return_value=SimpleNamespace(returncode=1, stdout=b"", stderr=b"boom"),
            ), patch("teacher_app.worker.libreoffice_warm.time.sleep"):
                self.assertFalse(runtime.warmup())
            self.assertFalse(runtime.warmed)
            self.assertIn("boom", runtime.status()["lastError"])
            runtime.close()

    def test_profile_is_persistent_across_restarts_and_stale_lock_removed(self):
        with tempfile.TemporaryDirectory() as temp_name:
            runtime = self._runtime(temp_name)
            with patch("teacher_app.worker.libreoffice_warm.subprocess.Popen", return_value=FakeProcess()), patch(
                "teacher_app.worker.libreoffice_warm.time.sleep"
            ):
                self.assertTrue(runtime.ensure_running())
                first = runtime.profile_arg
                marker = Path(temp_name) / "warm" / "font-cache.marker"
                marker.write_text("cached", encoding="utf-8")
                runtime.close()
                lock = Path(temp_name) / "warm" / "user" / ".lock"
                lock.parent.mkdir(parents=True, exist_ok=True)
                lock.write_text("stale", encoding="utf-8")
                self.assertTrue(runtime.ensure_running())
                second = runtime.profile_arg
            self.assertEqual(first, second)
            self.assertTrue(marker.exists())
            self.assertFalse(lock.exists())
            runtime.close()


class KokoroColdStartTests(unittest.TestCase):
    def setUp(self):
        self._env = patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for name in ("HF_HUB_OFFLINE", "KOKORO_HF_OFFLINE", "KOKORO_PRELOAD_ALL_VOICES", "HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE"):
            os.environ.pop(name, None)
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["HF_HOME"] = self._tmp.name
        media_audio_runtime._HF_OFFLINE_AUTO = False

    def tearDown(self):
        media_audio_runtime._HF_OFFLINE_AUTO = False
        self._env.stop()
        self._tmp.cleanup()

    def _cache_model(self, voice="zf_001"):
        repo = media_audio_runtime.DEFAULT_REPO_ID
        snap = Path(self._tmp.name) / "hub" / ("models--" + repo.replace("/", "--")) / "snapshots" / "abc"
        (snap / "voices").mkdir(parents=True)
        (snap / "config.json").write_text("{}", encoding="utf-8")
        (snap / "kokoro-v1_1-zh.pth").write_bytes(b"x")
        (snap / "voices" / f"{voice}.pt").write_bytes(b"x")

    def test_offline_auto_only_when_model_and_default_voice_cached(self):
        repo = media_audio_runtime.DEFAULT_REPO_ID
        self.assertFalse(media_audio_runtime._configure_hf_offline(repo, "zf_001"))
        self.assertNotIn("HF_HUB_OFFLINE", os.environ)
        self._cache_model()
        self.assertTrue(media_audio_runtime._configure_hf_offline(repo, "zf_001"))
        self.assertEqual(os.environ.get("HF_HUB_OFFLINE"), "1")
        # A not-yet-cached voice can re-enable the network once.
        self.assertTrue(media_audio_runtime._disable_auto_hf_offline())
        self.assertNotIn("HF_HUB_OFFLINE", os.environ)
        self.assertFalse(media_audio_runtime._disable_auto_hf_offline())

    def test_offline_respects_explicit_settings(self):
        repo = media_audio_runtime.DEFAULT_REPO_ID
        self._cache_model()
        os.environ["KOKORO_HF_OFFLINE"] = "0"
        self.assertFalse(media_audio_runtime._configure_hf_offline(repo, "zf_001"))
        self.assertNotIn("HF_HUB_OFFLINE", os.environ)
        os.environ["KOKORO_HF_OFFLINE"] = "auto"
        os.environ["HF_HUB_OFFLINE"] = "0"
        self.assertFalse(media_audio_runtime._configure_hf_offline(repo, "zf_001"))
        self.assertEqual(os.environ["HF_HUB_OFFLINE"], "0")
        self.assertFalse(media_audio_runtime._disable_auto_hf_offline())

    def _fake_pipeline(self):
        loaded = []

        class Pipeline:
            def load_voice(self, name):
                loaded.append(name)

            def __call__(self, *_args, **_kwargs):
                yield SimpleNamespace(audio=[0.0, 0.1])

        return Pipeline(), loaded

    def test_preload_loads_only_default_voice_and_reports_timings(self):
        pipeline, loaded = self._fake_pipeline()
        with patch.object(media_audio_runtime, "_kokoro_pipeline", return_value=pipeline):
            state = media_audio_runtime.preload_kokoro()
        self.assertEqual(loaded, [media_audio_runtime.DEFAULT_VOICE])
        self.assertTrue(state["warmed"])
        for key in ("importTorch", "createPipeline", "loadVoices", "firstSynthesis", "total"):
            self.assertIn(key, state["timings"])

    def test_preload_all_voices_is_opt_in(self):
        pipeline, loaded = self._fake_pipeline()
        os.environ["KOKORO_PRELOAD_ALL_VOICES"] = "true"
        with patch.object(media_audio_runtime, "_kokoro_pipeline", return_value=pipeline):
            media_audio_runtime.preload_kokoro()
        self.assertEqual(set(loaded), set(media_audio_runtime.ALLOWED_VOICES))


class AiWorkerStartupSourceTests(unittest.TestCase):
    def setUp(self):
        self.worker = (Path(__file__).resolve().parents[1] / "ai_question_worker.py").read_text(encoding="utf-8")

    def test_kokoro_warmup_runs_in_background_and_gates_tts_queues(self):
        self.assertIn("_start_kokoro_warmup()", self.worker)
        self.assertIn("name=\"teacher-kokoro-warmup\"", self.worker)
        self.assertIn("AI_WORKER_KOKORO_WARM_BLOCKING", self.worker)
        self.assertIn("if _KOKORO_WARM_DONE.is_set():\n                        did_work = audio_processor.run_next_queued() or did_work", self.worker)
        self.assertIn("if _KOKORO_WARM_DONE.is_set():\n                        did_work = video_processor.run_next_queued() or did_work", self.worker)
        # Non-TTS queues must not wait for the warmup.
        self.assertIn("did_work = question_processor.run_next_queued()", self.worker)


if __name__ == "__main__":
    unittest.main()
