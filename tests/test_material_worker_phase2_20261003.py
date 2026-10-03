import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from teacher_app.storage.worker_runtime import WorkerMaterialStorageAdapter
from teacher_app.worker import media_acceleration, media_transcode_compat
from teacher_app.worker.libreoffice_warm import WarmLibreOfficeConverter


class ProbeWorker:
    os = os
    calls = []
    outcomes = {}

    class subprocess:
        TimeoutExpired = subprocess.TimeoutExpired

        @staticmethod
        def run(command, **_kwargs):
            ProbeWorker.calls.append(list(command))
            encoder = ""
            if "-c:v" in command:
                encoder = command[command.index("-c:v") + 1]
            ok = bool(ProbeWorker.outcomes.get(encoder, False))
            return SimpleNamespace(
                returncode=0 if ok else 1,
                stdout="",
                stderr="" if ok else f"{encoder} unavailable",
            )

    @staticmethod
    def _bin(_env_name, _fallback):
        return "ffmpeg"


class FakeProcess:
    def __init__(self):
        self.returncode = None
        self.terminated = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.returncode = -9


class MaterialWorkerPhase220261003Tests(unittest.TestCase):
    def setUp(self):
        media_acceleration.reset_cache()
        ProbeWorker.calls = []
        ProbeWorker.outcomes = {}

    def test_real_probe_prefers_qsv_and_stops_after_success(self):
        ProbeWorker.outcomes = {"h264_qsv": True, "h264_nvenc": True}
        with patch.dict(
            os.environ,
            {
                "MATERIAL_VIDEO_HARDWARE_ACCELERATION": "true",
                "MATERIAL_VIDEO_HARDWARE_ENCODER": "auto",
            },
            clear=False,
        ):
            result = media_acceleration.detect_h264_encoder(ProbeWorker)
        self.assertTrue(result["available"])
        self.assertEqual(result["selected"], "h264_qsv")
        self.assertEqual(len(ProbeWorker.calls), 1)

    def test_probe_moves_to_nvenc_when_qsv_is_not_usable(self):
        ProbeWorker.outcomes = {
            "h264_qsv": False,
            "h264_nvenc": True,
        }
        with patch.dict(
            os.environ,
            {
                "MATERIAL_VIDEO_HARDWARE_ACCELERATION": "true",
                "MATERIAL_VIDEO_HARDWARE_ENCODER": "auto",
            },
            clear=False,
        ):
            result = media_acceleration.detect_h264_encoder(ProbeWorker)
        self.assertEqual(result["selected"], "h264_nvenc")
        self.assertEqual(
            [
                call[call.index("-c:v") + 1]
                for call in ProbeWorker.calls
            ],
            ["h264_qsv", "h264_nvenc"],
        )

    def test_cpu_preference_skips_all_hardware_probes(self):
        with patch.dict(
            os.environ,
            {
                "MATERIAL_VIDEO_HARDWARE_ACCELERATION": "true",
                "MATERIAL_VIDEO_HARDWARE_ENCODER": "cpu",
            },
            clear=False,
        ):
            result = media_acceleration.detect_h264_encoder(ProbeWorker)
        self.assertFalse(result["available"])
        self.assertEqual(result["selected"], "")
        self.assertEqual(ProbeWorker.calls, [])

    def test_ffmpeg_progress_time_parser_uses_real_clock(self):
        self.assertAlmostEqual(
            media_transcode_compat._parse_ffmpeg_time("00:12:34.500000"),
            754.5,
            places=3,
        )
        self.assertEqual(media_transcode_compat._parse_ffmpeg_time("invalid"), 0.0)

    def test_ffmpeg_streaming_runner_emits_out_time_progress(self):
        class Stream:
            def __init__(self, lines):
                self.lines = list(lines)

            def __iter__(self):
                return iter(self.lines)

        class Process:
            def __init__(self):
                self.stdout = Stream(
                    [
                        "out_time=00:00:02.500000\n",
                        "out_time=00:00:05.000000\n",
                        "progress=end\n",
                    ]
                )
                self.stderr = Stream([])
                self.returncode = 0

            def poll(self):
                return self.returncode

            def wait(self, timeout=None):
                return self.returncode

            def terminate(self):
                self.returncode = 0

            def kill(self):
                self.returncode = -9

        calls = []

        class FakeSubprocess:
            PIPE = object()
            TimeoutExpired = subprocess.TimeoutExpired

            @staticmethod
            def Popen(command, **_kwargs):
                calls.append(list(command))
                return Process()

        class Worker:
            subprocess = FakeSubprocess

        with tempfile.TemporaryDirectory() as temp_name:
            output = Path(temp_name) / "out.mp4"
            output.write_bytes(b"video")
            progress = []
            completed, error = media_transcode_compat._run(
                Worker,
                ["ffmpeg", "-y", "-i", "in.mov", str(output)],
                output,
                timeout=5,
                progress_callback=lambda current, total: progress.append((current, total)),
                duration_seconds=5.0,
            )

        self.assertEqual(error, "")
        self.assertEqual(completed.returncode, 0)
        self.assertTrue(progress)
        self.assertIn((2.5, 5.0), progress)
        self.assertEqual(progress[-1], (5.0, 5.0))
        self.assertIn("-progress", calls[0])
        self.assertIn("pipe:1", calls[0])

    def test_warm_libreoffice_reuses_one_profile_for_conversion(self):
        fake_process = FakeProcess()
        with tempfile.TemporaryDirectory() as temp_name,              patch("teacher_app.worker.libreoffice_warm.subprocess.Popen", return_value=fake_process),              patch("teacher_app.worker.libreoffice_warm.time.sleep"):
            runtime = WarmLibreOfficeConverter("soffice", enabled=True, startup_timeout=1)

            def fake_run(command, **_kwargs):
                out_dir = Path(command[command.index("--outdir") + 1])
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / "deck.pdf").write_bytes(b"%PDF-warm")
                return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

            with patch(
                "teacher_app.worker.libreoffice_warm.subprocess.run",
                side_effect=fake_run,
            ) as run:
                source = Path(temp_name) / "deck.pptx"
                source.write_bytes(b"pptx")
                output = runtime.convert_to_pdf(
                    source,
                    Path(temp_name) / "out",
                    timeout=30,
                )

            self.assertTrue(output.is_file())
            command = run.call_args.args[0]
            self.assertIn(runtime.profile_arg, command)
            self.assertTrue(runtime.running)
            runtime.close()

    def test_warm_failure_restarts_once_then_falls_back_to_oneshot(self):
        with patch.dict(
            os.environ,
            {"MATERIAL_LIBREOFFICE_WARM_ENABLED": "true"},
            clear=False,
        ):
            runtime = WorkerMaterialStorageAdapter()
        fallback = Path("fallback.pdf")
        with patch.object(
            runtime._libreoffice_warm,
            "convert_to_pdf",
            side_effect=[RuntimeError("warm died"), RuntimeError("warm retry died")],
        ) as warm, patch.object(
            runtime._libreoffice_warm,
            "restart",
            return_value=True,
        ) as restart, patch.object(
            runtime,
            "_office_to_pdf_once",
            return_value=fallback,
        ) as one_shot:
            result = runtime._office_to_pdf(
                Path("deck.pptx"),
                Path("."),
                timeout=30,
            )

        self.assertEqual(result, fallback)
        self.assertEqual(warm.call_count, 2)
        restart.assert_called_once()
        one_shot.assert_called_once()
        self.assertEqual(runtime.libreoffice_status()["mode"], "oneshot")
        self.assertIn("warm retry died", runtime.libreoffice_status()["fallback"])


if __name__ == "__main__":
    unittest.main()
