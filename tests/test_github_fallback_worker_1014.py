from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class GithubMaterialFallback1014Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = ROOT.joinpath("tools", "github_fallback_worker.py").read_text(encoding="utf-8")
        cls.workflow = ROOT.joinpath(".github", "workflows", "material-fallback-worker.yml").read_text(encoding="utf-8")

    def test_runner_reuses_canonical_worker_protocol_and_is_bounded(self):
        for marker in (
            "material_worker as worker",
            "WorkerApi",
            "/api/material-worker/claim",
            "process_one",
            "MATERIAL_FALLBACK_MAX_JOBS",
            "refusing to claim jobs",
        ):
            self.assertIn(marker, self.runner)

    def test_runner_requires_office_and_media_conversion_capabilities(self):
        for marker in ("ffmpeg", "ffprobe", "libreOffice"):
            self.assertIn(marker, self.runner)

    def test_local_worker_gets_a_grace_period_before_fallback_claims(self):
        self.assertIn("MATERIAL_FALLBACK_GRACE_SECONDS", self.runner)
        self.assertIn("time.sleep(grace)", self.runner)
        self.assertIn('MATERIAL_FALLBACK_GRACE_SECONDS: "300"', self.workflow)

    def test_workflow_is_ephemeral_free_tool_fallback(self):
        for marker in (
            'cron: "7,22,37,52 * * * *"',
            "workflow_dispatch",
            "runs-on: ubuntu-latest",
            "libreoffice ffmpeg qpdf",
            "MATERIAL_STORAGE_BACKEND: gdrive",
            "python -u tools/github_fallback_worker.py",
            "timeout-minutes: 30",
        ):
            self.assertIn(marker, self.workflow)

    def test_workflow_uses_secrets_without_literal_credentials(self):
        for name in (
            "MATERIAL_WORKER_TOKEN",
            "GDRIVE_CLIENT_ID",
            "GDRIVE_CLIENT_SECRET",
            "GDRIVE_REFRESH_TOKEN",
            "GDRIVE_FOLDER_ID",
        ):
            self.assertIn("${{ secrets." + name + " }}", self.workflow)
        self.assertNotIn("GDRIVE_CLIENT_SECRET: '", self.workflow)


if __name__ == "__main__":
    unittest.main()
