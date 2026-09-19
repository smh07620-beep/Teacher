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

## Windows 安全自動更新（6.8.1）

第一次仍須由院內人員把 repository 更新到含本功能的版本，並建立
`.venv`。Worker 不再自動追蹤 `main`。只有明確設定核准的 annotated release
tag 時，更新器才會抓取該 tag；預設還會執行 `git verify-tag` 驗證簽章，並可
再用核准 commit SHA 做第二層 pin。更新器只允許 fast-forward 到這個已核准
release，不會切換 branch、變更 remote、stash、reset 或讀出
`.local-worker.env`。

執行中的 Worker 只有在 `MATERIAL_WORKER_AUTO_UPDATE=true` 時才會啟用更新
檢查，且只在沒有 claimed/processing job 時執行。
發現並成功安裝新版時，Worker 以 exit code `75` 請 launcher 重啟；不會在
Python process 中 hot reload。更新、fetch 或依賴同步失敗時，launcher 會記錄
不含 secrets 的警告，並繼續嘗試啟動既有本機版本。可設定：

```text
MATERIAL_WORKER_AUTO_UPDATE=false
MATERIAL_WORKER_UPDATE_INTERVAL_HOURS=6
MATERIAL_WORKER_RELEASE_REF=v6.8.1
# 可選：再 pin 到核准 commit 的 7–40 碼 SHA
MATERIAL_WORKER_RELEASE_COMMIT=abcdef1
# 預設 true；正式環境建議維持簽章驗證
MATERIAL_WORKER_REQUIRE_SIGNED_TAG=true
```

interval 最低為一小時。要手動安全檢查，先設定核准的 release tag，再在
repository root 執行 `./update_material_worker.ps1`。此 script 拒絕 dirty
tree、缺少 `origin`、非 annotated tag、簽章驗證失敗、commit pin 不符、
diverged history 或 fetch 失敗，並保留目前 checkout。

Task Scheduler 請使用唯一 canonical entrypoint（工作目錄為
`C:\TeacherWorker`）：

```text
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\TeacherWorker\run_material_worker_autostart.ps1"
```

launcher 在每次啟動前檢查 `.venv\Scripts\python.exe`、Python imports、
FFmpeg/FFprobe、LibreOffice 和 MEGAcmd capability。它只在 `requirements.txt`
checksum 改變或 import check 失敗時同步 requirements；一般 crash 最多重啟
五次，避免 tight restart loop。

管理後台「大型教材背景工作」會顯示 Worker version、short SHA、branch、
capability 與最近更新檢查時間。若 heartbeat 知道本機剛成功取得新版但尚未
restart，會顯示「⚠ Worker 有新版待更新」。Render 只接收和顯示這些非敏感
metadata，不能命令醫院 Worker pull。

## Start, stop, update and logs

Windows PowerShell: `./run_material_worker_autostart.ps1` (or the compatible
`./run_material_worker.ps1`).

Windows cmd: `run_material_worker.bat`.

Linux: export the same variables and run `python -u material_worker.py`.
Stop with Ctrl+C. To update, pull the approved Teacher commit, rerun dependency
installation when `requirements.txt` changes, then restart the script. Capture
stdout/stderr through Task Scheduler or your usual local log collector.

For automatic startup, create a Windows Task Scheduler task triggered **At log
on**, choose “Run whether user is logged on or not” only if the credential store
and MEGA client are available to that account, and use the canonical command
shown above. Do not expose any inbound firewall rule: all Worker communication
is outbound HTTPS.

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
