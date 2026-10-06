"""Run isolated F/G full-stack Web/Worker/R2-compatible processes."""
from __future__ import annotations
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

import boto3
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    os.chdir(ROOT)
    os.environ.update({
        "R2_ACCESS_KEY_ID": "ci",
        "R2_SECRET_ACCESS_KEY": "ci-secret",
        "R2_ACCOUNT_ID": "ci",
        "R2_BUCKET_NAME": "teacher-ai-fg-e2e",
        "R2_ENDPOINT_URL": "http://127.0.0.1:9002",
        "R2_REGION": "us-east-1",
        "AI_WORKER_TOKEN": secrets.token_urlsafe(32),
        "AI_WORKER_TRANSPORT": "https",
        "AI_WORKER_ALLOW_INSECURE_LOCAL_HTTP": "true",
        "TEACHER_BASE_URL": "http://127.0.0.1:4177",
        "TEACHER_AI_FG_FULLSTACK_BASE_URL": "http://127.0.0.1:4177",
        "TEACHER_E2E_TEST_MODE": "1",
        "TEACHER_E2E_DETERMINISTIC_STUBS": "1",
        "TEACHER_AI_FG_FULLSTACK_RUN": "1",
        "AI_EXTERNAL_PROCESSING_ENABLED": "true",
        "AI_EXTERNAL_MEDIA_ENABLED": "true",
        # Production privacy stays fail-closed. Only this double-opt-in isolated
        # fixture may exercise video-question generation from local media.
        "AI_EXTERNAL_MEDIA_ALLOWED": "true",
        "TEACHER_CI_BROWSER_PASSWORD": secrets.token_urlsafe(24),
        "MATERIAL_WORKER_TOKEN": secrets.token_urlsafe(32),
        "MATERIAL_WORKER_ALLOW_INSECURE_LOCALHOST": "true",
        "MATERIAL_STORAGE_BACKEND": "r2",
        "MATERIAL_SHARED_STAGING_BACKEND": "r2",
        "MATERIAL_WORKER_ENABLED": "true",
        "MATERIAL_DIRECT_UPLOAD_ENABLED": "true",
        "MATERIAL_BACKGROUND_JOBS": "false",
        "MATERIAL_WORKER_HEARTBEAT_SECONDS": "5",
        "MATERIAL_WORKER_HTTP_RATE_LIMIT_PER_MINUTE": "1800",
        "AI_QUESTION_JOB_MAX_PER_MINUTE": "30",
        "MEDIA_SUBTITLE_JOB_MAX_PER_MINUTE": "30",
        "MEDIA_AUDIO_JOB_MAX_PER_MINUTE": "30",
        "AI_VIDEO_JOB_MAX_PER_MINUTE": "10",
        "AI_VIDEO_STORAGE_BACKEND": "r2",
        "AI_PRESENTATION_STORAGE_BACKEND": "r2",
        "AI_PRESENTATION_FALLBACK_TO_R2": "true",
        "AI_VIDEO_FALLBACK_TO_R2": "true",
    })
    processes, logs = [], []

    def start(name, args, env=None):
        log = open(f"ai-fg-{name}.log", "w", encoding="utf-8")
        logs.append(log)
        processes.append(subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, env=env))

    def ready(url):
        for _ in range(90):
            try:
                if requests.get(url, timeout=1).ok:
                    return
            except requests.RequestException:
                pass
            time.sleep(.5)
        raise RuntimeError(f"Fixture failed to start: {url}")

    try:
        start("s3", [sys.executable, "-m", "moto.server", "-H", "127.0.0.1", "-p", "9002"])
        ready("http://127.0.0.1:9002/")
        client = boto3.client(
            "s3", endpoint_url=os.environ["R2_ENDPOINT_URL"],
            aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
            region_name=os.environ["R2_REGION"],
        )
        client.create_bucket(Bucket=os.environ["R2_BUCKET_NAME"])
        client.put_bucket_cors(Bucket=os.environ["R2_BUCKET_NAME"], CORSConfiguration={"CORSRules": [{
            "AllowedOrigins": ["http://127.0.0.1:4177"],
            "AllowedMethods": ["GET", "PUT", "POST", "HEAD"],
            "AllowedHeaders": ["*"], "ExposeHeaders": ["ETag"],
        }]})

        start("web", [sys.executable, "tests/ai_fg_fullstack_server.py"])
        ready("http://127.0.0.1:4177/ready")

        worker_env = dict(os.environ)
        bootstrap = str(ROOT / "tests" / "e2e_ai_fg_bootstrap")
        worker_env["PYTHONPATH"] = bootstrap + os.pathsep + str(ROOT) + (
            os.pathsep + worker_env["PYTHONPATH"] if worker_env.get("PYTHONPATH") else ""
        )
        start("worker", [sys.executable, "ai_question_worker.py"], env=worker_env)
        start("material-worker", [sys.executable, "-m", "teacher_app.worker.material_worker_entry"])

        node = os.environ.get("E2E_NODE", "node")
        return subprocess.call([
            node, "node_modules/@playwright/test/cli.js", "test",
            *sys.argv[1:], "--reporter=line", "--workers=1",
        ])
    finally:
        for process in reversed(processes):
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
        for log in logs:
            log.close()


if __name__ == "__main__":
    raise SystemExit(main())
