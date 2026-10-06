"""Run isolated real Web/Worker/S3 processes identically locally and in CI."""
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import tempfile

import boto3
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    os.chdir(ROOT)
    os.environ.update({
        "R2_ACCESS_KEY_ID": "ci", "R2_SECRET_ACCESS_KEY": "ci-secret",
        "R2_ACCOUNT_ID": "ci", "R2_BUCKET_NAME": "teacher-ai-media-e2e",
        "R2_ENDPOINT_URL": "http://127.0.0.1:9001", "R2_REGION": "us-east-1",
        "AI_WORKER_TOKEN": secrets.token_urlsafe(32), "AI_WORKER_TRANSPORT": "https",
        "AI_WORKER_ALLOW_INSECURE_LOCAL_HTTP": "true",
        "TEACHER_BASE_URL": "http://127.0.0.1:4176",
        "TEACHER_E2E_TEST_MODE": "1", "TEACHER_E2E_DETERMINISTIC_STUBS": "1",
        "TEACHER_AI_FULLSTACK_RUN": "1",
        "AI_EXTERNAL_PROCESSING_ENABLED": "true",
        "TEACHER_CI_BROWSER_PASSWORD": secrets.token_urlsafe(24),
        "E2E_PYTHON": sys.executable,
        "MATERIAL_WORKER_TOKEN": secrets.token_urlsafe(32),
        "MATERIAL_WORKER_ALLOW_INSECURE_LOCALHOST": "true",
        "MATERIAL_STORAGE_BACKEND": "r2", "MATERIAL_SHARED_STAGING_BACKEND": "r2",
        "MATERIAL_WORKER_ENABLED": "true", "MATERIAL_DIRECT_UPLOAD_ENABLED": "true",
        "MATERIAL_BACKGROUND_JOBS": "false",
        "MATERIAL_WORKER_HEARTBEAT_SECONDS": "5",
        "MATERIAL_WORKER_HTTP_RATE_LIMIT_PER_MINUTE": "1800",
        "MEDIA_SCRIPT_JOB_MAX_PER_MINUTE": "30",
    })
    processes, logs = [], []

    def start(name, args):
        log = open(f"ai-media-{name}.log", "w", encoding="utf-8")
        logs.append(log)
        processes.append(subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT))

    def ready(url):
        for _ in range(60):
            try:
                if requests.get(url, timeout=1).ok:
                    return
            except requests.RequestException:
                pass
            time.sleep(.5)
        raise RuntimeError(f"Fixture failed to start: {url}")

    try:
        start("s3", [sys.executable, "-m", "moto.server", "-H", "127.0.0.1", "-p", "9001"])
        ready("http://127.0.0.1:9001/")
        client = boto3.client("s3", endpoint_url=os.environ["R2_ENDPOINT_URL"],
                     aws_access_key_id="ci", aws_secret_access_key="ci-secret",
                     region_name="us-east-1")
        client.create_bucket(Bucket=os.environ["R2_BUCKET_NAME"])
        client.put_bucket_cors(Bucket=os.environ["R2_BUCKET_NAME"], CORSConfiguration={"CORSRules":[{
            "AllowedOrigins":["http://127.0.0.1:4176"], "AllowedMethods":["GET","PUT","POST","HEAD"],
            "AllowedHeaders":["*"], "ExposeHeaders":["ETag"]}]})
        fixture_dir = Path(tempfile.mkdtemp(prefix="ai-source-formats-"))
        os.environ["E2E_SOURCE_DIR"] = str(fixture_dir)
        from tests.ai_source_fixtures import build
        build(fixture_dir)
        start("web", [sys.executable, "tests/ai_media_fullstack_server.py"])
        ready("http://127.0.0.1:4176/ready")
        start("worker", [sys.executable, "ai_question_worker.py"])
        start("material-worker", [sys.executable, "-m", "teacher_app.worker.material_worker_entry"])
        node = os.environ.get("E2E_NODE", "node")
        return subprocess.call([node, "node_modules/@playwright/test/cli.js", "test",
                                *sys.argv[1:], "--reporter=line", "--workers=1"])
    finally:
        for process in reversed(processes):
            process.terminate()
            process.wait(timeout=15)
        for log in logs:
            log.close()


if __name__ == "__main__":
    raise SystemExit(main())
