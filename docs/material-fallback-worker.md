# Free material fallback Worker

The hospital Windows Worker remains the primary executor. The fallback is an ephemeral GitHub Actions runner that reuses the same HTTPS material-worker queue and exits after at most three jobs.

It is designed for two failure classes:

- LibreOffice is missing/unavailable on the Windows Worker, so Office documents cannot be converted.
- FFmpeg/FFprobe is missing/unavailable on the Windows Worker, so video/audio normalization cannot run.

The fallback workflow installs LibreOffice, FFmpeg, FFprobe and qpdf on an Ubuntu GitHub-hosted runner, then runs `github_fallback_worker.py`. It uses Google Drive as final storage and does not receive `DATABASE_URL`.

## Required GitHub repository secrets

Configure these in GitHub repository Actions secrets before the fallback can process a job:

```text
MATERIAL_WORKER_TOKEN
GDRIVE_CLIENT_ID
GDRIVE_CLIENT_SECRET
GDRIVE_REFRESH_TOKEN
GDRIVE_FOLDER_ID
```

Do not copy secrets into the workflow file or source code. When one or more secrets are absent, the workflow exits successfully without claiming a job.

## Schedule and ownership

`.github/workflows/material-fallback-worker.yml` runs every 15 minutes and can also be started manually. Queue claim is atomic on the Web service, so a Windows Worker and the fallback cannot own the same queued job simultaneously. The fallback processes at most three jobs per run and then exits.

If a Windows Worker died after claiming a job, the existing stale-job recovery applies before a later claim. The fallback does not bypass heartbeat/ownership, publish receipt, source hash verification, or normal completion acknowledgement.

This workflow is a recovery path, not a replacement for investigating the Windows Worker. Local LibreOffice/FFmpeg should still be repaired when practical.
