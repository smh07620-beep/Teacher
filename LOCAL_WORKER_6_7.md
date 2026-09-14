# Teacher 6.7 B-Free Local Material Worker

This worker runs on a trusted hospital Windows 10/11 or Linux machine. It does
not open an inbound port and does not need `DATABASE_URL`. It makes outbound
HTTPS calls to the Teacher Web Worker API, downloads R2 staging through a
short-lived signed URL, and publishes final material directly to MEGA (primary)
or Google Drive (fallback) using credentials stored only on that local machine.

Existing small uploads remain compatible when R2 direct upload is not set up:
after an atomic claim the Worker obtains that one source through a
token-protected HTTPS download endpoint. It is not used for large R2 uploads.

## Install and configure

1. Install Python 3.12 and run `python -m pip install -r requirements.txt`.
2. Install FFmpeg/FFprobe and LibreOffice; leave them on `PATH`, or set
   `FFMPEG_PATH`, `FFPROBE_PATH`, and `SOFFICE_PATH` to absolute executable
   paths. The startup log clearly reports unavailable capabilities.
3. Copy the following into a local-only `.local-worker.env` (it is gitignored):

```text
TEACHER_BASE_URL=https://your-teacher.example
MATERIAL_WORKER_TOKEN=long-random-secret-from-Render
MEGA_EMAIL=...
MEGA_PASSWORD=...
MEGA_ROOT_FOLDER=smh-teaching-materials
# Optional Google Drive fallback credentials
GDRIVE_CLIENT_ID=...
GDRIVE_CLIENT_SECRET=...
GDRIVE_REFRESH_TOKEN=...
GDRIVE_FOLDER_ID=...
```

Never put this file, database URLs, R2 access keys, or storage credentials in
Git. The Worker token only permits the narrow material job API and is distinct
from `ADMIN_KEY`.

## Start, stop, update and logs

Windows PowerShell: `./run_material_worker.ps1`.

Windows cmd: `run_material_worker.bat`.

Linux: export the same variables and run `python -u material_worker.py`.
Stop with Ctrl+C. To update, pull the approved Teacher commit, rerun dependency
installation when `requirements.txt` changes, then restart the script. Capture
stdout/stderr through Task Scheduler or your usual local log collector.

For automatic startup, create a Windows Task Scheduler task triggered **At log
on**, choose “Run whether user is logged on or not” only if the credential store
and MEGA client are available to that account, and use PowerShell with
`-File C:\path\Teacher\run_material_worker.ps1`. Do not expose any inbound
firewall rule: all Worker communication is outbound HTTPS.

## R2 CORS for browser multipart upload

Configure this on the R2 bucket, replacing the origin with the production
Teacher hostname. Do not use `*` for production.

```json
[
  {
    "AllowedOrigins": ["https://your-teacher.example"],
    "AllowedMethods": ["PUT", "POST", "GET", "HEAD"],
    "AllowedHeaders": ["content-type", "x-amz-*"],
    "ExposeHeaders": ["etag"],
    "MaxAgeSeconds": 300
  }
]
```

For local browser development, add a specific `http://localhost:<port>` origin
temporarily; remove it from production CORS afterwards.
