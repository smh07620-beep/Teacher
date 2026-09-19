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
3. Copy the tracked, non-secret template to the local-only `.local-worker.env`
   (the destination is gitignored), then replace placeholders only on the Worker
   host:

```powershell
Copy-Item .local-worker.env.example .local-worker.env
```

The template contains these required/release settings plus optional storage
placeholders:

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
# Claimed-job heartbeat during long FFmpeg/LibreOffice/cloud operations.
MATERIAL_WORKER_HEARTBEAT_SECONDS=30
# Safe release updater. Runtime auto-check remains opt-in by default.
MATERIAL_WORKER_AUTO_UPDATE=false
MATERIAL_WORKER_UPDATE_INTERVAL_HOURS=6
MATERIAL_WORKER_RELEASE_REF=v6.8.1
# Optional second pin to the approved tag's 7–40 character commit SHA.
MATERIAL_WORKER_RELEASE_COMMIT=
# Keep true for production signed annotated release tags.
MATERIAL_WORKER_REQUIRE_SIGNED_TAG=true
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

`MATERIAL_WORKER_AUTO_UPDATE` 的程式預設值是 `false`。執行中的 Worker 只有在
明確設定 `MATERIAL_WORKER_AUTO_UPDATE=true` 時才會啟用週期更新檢查，且只在
沒有 claimed/processing job 時執行。Windows launcher 每次啟動時仍會呼叫安全
updater；若 `.local-worker.env` 沒有 `MATERIAL_WORKER_RELEASE_REF`，updater 會拒絕
更新並以既有版本啟動 Worker。
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

Worker 在 claimed job 執行期間預設每 30 秒送出一次 heartbeat，包含下載、
FFmpeg/LibreOffice 轉檔與 MEGA/Google Drive publish。可用
`MATERIAL_WORKER_HEARTBEAT_SECONDS` 調整為 5–90 秒；heartbeat 暫時失敗只會記錄
不含 secret 的警告，不會中斷正在進行的本機轉檔或上傳。publish 完成後若
`/complete` 回應因短暫網路／5xx／429 遺失，Worker 會先重送同一份 completion
result；Web 端對已完成且同一 Worker ownership 的 completion replay 會直接回覆
成功，避免因單次 acknowledgement 遺失立刻重新轉檔與重新 publish。

Web/Render 端的 stale-processing recovery 使用 `MATERIAL_JOB_STALE_SECONDS`，
預設 `1800` 秒，允許範圍 300–21600 秒。這個值應明顯大於本機 heartbeat interval；
預設 30 秒 heartbeat 對 1800 秒 stale threshold 有 60 倍餘裕。每次 Worker claim
前，Web 會檢查超過 threshold 的 `processing` job：若 shared staging 還存在就重新
排隊，若 staging 已不存在就標記失敗。恢復時使用 status + worker ownership +
`updated_at` compare-and-set，因此 recovery 讀到舊 snapshot 後若 Worker 剛送出新的
heartbeat，新的 heartbeat 會勝出，舊 recovery 不會覆寫它。此設定屬於 Web/Render
環境，不必放進 `.local-worker.env`。

Task Scheduler 請使用唯一 canonical entrypoint（工作目錄為
`C:\TeacherWorker`）：

```text
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\TeacherWorker\run_material_worker_autostart.ps1"
```

launcher 在每次啟動前檢查 `.venv\Scripts\python.exe`、Python imports、
FFmpeg/FFprobe、LibreOffice 和 MEGAcmd capability。它只在 `requirements.txt`
checksum 改變或 import check 失敗時同步 requirements；一般 crash 最多重啟
五次，避免 tight restart loop。

正式 Windows 常駐執行請用 repository 內的
`install_material_worker_task.ps1`。installer 會建立 **At startup** trigger，
action 只指向 `run_material_worker_autostart.ps1`，並在 Task Scheduler 層設定
失敗後每 1 分鐘重啟、最多 5 次及 `StartWhenAvailable`。Worker token、MEGA、
Google Drive 等 secrets 不會放進 Task Scheduler command line；仍只從本機、
gitignored 的 `.local-worker.env` 載入。

一般 Windows/domain 帳號使用 `Password` logon type，因此即使使用者沒有登入也
可以執行，對應 Task Scheduler 的 **Run whether user is logged on or not** 語意。
請從 **系統管理員身分的 Windows PowerShell** 執行；若未傳入
`-Credential`，installer 會用 `Get-Credential` 互動式詢問該 Windows 帳號密碼：

```powershell
cd C:\TeacherWorker
.\install_material_worker_task.ps1 -TaskUser "HOSPITAL\teacher-worker" -StartNow
```

密碼只傳給 Windows Task Scheduler 的註冊 API，不會寫入 repository、`.env`、
task action arguments 或 log。若使用 Windows well-known service identity
（`SYSTEM`、`LOCAL SERVICE`、`NETWORK SERVICE`），可改用 `ServiceAccount` logon
type，不需要密碼：

```powershell
.\install_material_worker_task.ps1 `
  -TaskUser "NT AUTHORITY\SYSTEM" `
  -ServiceAccount `
  -StartNow
```

只有在該 service identity 已有 repository、`.local-worker.env`、MEGAcmd/Google
Drive credential store 的必要存取權時才適合。一般 domain/local 專用 service user
仍使用上面的 `Password` 模式。Task 執行 identity 必須能讀取
`C:\TeacherWorker` 與 `.local-worker.env`，且必須能使用該帳號所需的雲端
credential/cache；installer 不會修改檔案 ACL 或搬移任何 credentials。

### Windows Application Event Log

從 elevated PowerShell 執行 `install_material_worker_task.ps1` 時，installer 也會
idempotently 確認 Windows **Application** log 的 event source
`TeacherMaterialWorker` 已存在；不存在時才建立。若同名 source 已被註冊到其他
Windows log，installer 會拒絕破壞性搬移／重建，需由系統管理者先確認既有註冊。
此功能直接使用 Windows / PowerShell Event Log API，不需要 `pywin32`。

canonical `run_material_worker_autostart.ps1` 只寫 bounded、非敏感的 supervisor
事件：1000/1001/1010 為啟動、安全 updater 與核准更新後 restart 的
**Information**；2001/2002/2100 為 updater 缺失／拒絕或失敗、Worker abnormal
exit/restart 的 **Warning**；3001–3004 為必要連線設定缺失、venv/啟動 prerequisite、
process launch failure 與 retry exhaustion 的 **Error**。Event Log source/ACL/service
若暫時不可用，只會 fallback 到 `Write-Warning` / host，不會阻止 Worker 啟動或重啟。

Event Log 訊息不包含 `.local-worker.env` 值、password/token、provider credentials、
raw command arguments 或檔案內容。單一教材工作的轉檔／publish 失敗仍留在既有 Web
job/audit DB 與 Worker stdout/stderr，不會把每一筆教材工作灌入 Windows Event Log。
Task Scheduler 自己的 **Operational** log 仍是 Windows 排程器的獨立紀錄，不與
`TeacherMaterialWorker` Application events 混用。

管理後台「大型教材背景工作」會顯示 Worker version、short SHA、branch、
capability 與最近更新檢查時間。若 heartbeat 知道本機剛成功取得新版但尚未
restart，會顯示「⚠ Worker 有新版待更新」。Render 只接收和顯示這些非敏感
metadata，不能命令醫院 Worker pull。

## Start, stop, update and logs

Windows PowerShell: `./run_material_worker_autostart.ps1` (or the compatible
`./run_material_worker.ps1`).

Windows cmd: `run_material_worker.bat`（相容入口；會委派給同一個 canonical
PowerShell supervisor）。

Linux: export the same variables and run `python -u material_worker.py`.
Stop with Ctrl+C. To update, pull the approved Teacher commit, rerun dependency
installation when `requirements.txt` changes, then restart the script. Capture
stdout/stderr through Task Scheduler or your usual local log collector.

For automatic startup, use `install_material_worker_task.ps1`. It registers an
**At startup** task with password-logon or service-account semantics so the
Worker can run whether a user is logged on or not, and it adds task-level
restart-on-failure around the canonical supervisor. Do not expose any inbound
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
