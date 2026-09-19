# Teacher 醫學檢驗教學平台

目前正式 release contract 版本為 **`6.8.1`**。Repository 內的 7.x 名稱是功能、UI 與 convergence 的內部世代；目前已到 **`7.9 / RC79`** 標記，但這不等於正式 SemVer 已升版。正式版本永遠以 `VERSION` / `release_contract.py` 為準。產品功能與 Release Candidate 暴露狀態請以 `RC_FEATURE_UI_COVERAGE_MATRIX.md` 為準；`FEATURE_EXPOSURE_681.md` 僅保留為歷史 release record。

本系統是 Flask + HTML/JavaScript 的醫學檢驗教育訓練平台，涵蓋課程、教材、考卷、題庫、成績、PGY 流程、教師評核與管理後台。正式 Web entrypoint 是 `pgy_app:app`。

## 目前架構

### Web / Render

Render 只執行 Web Service：

```text
bash run_web.sh
→ gunicorn ... pgy_app:app
```

預設 Gunicorn 為 1 worker × 4 threads，可由 `WEB_CONCURRENCY`、`GUNICORN_THREADS` 與 `GUNICORN_TIMEOUT` 調整。`/health` 是 Render health check。

正式部署使用 `DATABASE_URL` 連接 PostgreSQL／Supabase；`render.yaml` 的 `DATABASE_URL` 為 `sync: false`，因此必須在部署環境提供正確連線字串。本機未設定 `DATABASE_URL` 時才使用 SQLite fallback。

### 認證與權限

一般教學與管理流程使用登入 session + server-side RBAC。瀏覽器不再要求使用者輸入或保存公開的固定 `ADMIN_KEY`。部分舊模組仍會呼叫 `getAdminKey()` 並送出相容 header，但目前它只是 session-RBAC compatibility seam，不是額外的授權來源。

敏感系統操作仍依既有 elevation / RBAC 規則處理；前端顯示角色、職稱或 responsibility metadata 都不能取代 server-side authorization。

### 教材上傳與背景處理

教材建立從後台的「＋ 建立教學內容」統一入口開始。舊教材上傳 DOM 仍保留作 canonical executor，但不是第二套一般使用者建立入口。

Render Web 不 fork `material_worker.py`；教材的背景轉檔、最佳化與正式儲存由另外運行的本機／院內 Worker 經 HTTPS worker API 處理：

```text
python -u material_worker.py
```

Worker 使用獨立的 `MATERIAL_WORKER_TOKEN`，不需要 production `DATABASE_URL`，也不持有學員 session。

目前 Web image 仍不能移除全部媒體工具。`/api/slides/upload` 的同步相容路徑仍可用 LibreOffice / qpdf 處理 Office/PDF；Groq 影片 AI 出題仍在 Web process 以 FFmpeg/ffprobe 擷取音訊與代表畫面；舊 Office 格式的 AI 文字擷取也會使用 LibreOffice。MEGAcmd 則同時服務 Web 端的 MEGA 教材讀取、下載、刪除與容量狀態查詢。等這些 Web caller 全部遷移後，才可把 LibreOffice / FFmpeg 從 Web Docker image 拆到 Worker-only 安裝流程。

大型檔案採 Browser → Cloudflare R2 multipart direct upload。R2 是 shared staging；Worker claim job 後再下載、驗證 byte count / SHA-256 / 檔案格式並處理。小型檔案保留 Web compatible upload path，但轉檔仍由 Worker 負責。正式內容儲存沿用目前 provider policy；相關細節請見 `ARCHITECTURE.md` 與 `LOCAL_WORKER_6_7.md`。

## 考試與成績

- 考卷與題庫由 server-side RBAC 保護。
- 開始考試會建立 server-side attempt；前端已有同一考卷 in-flight start deduplication。
- 計分由伺服器決定，客戶端不能覆寫分數或正確答案。
- 同一 attempt 重複／併發提交只允許第一次完成計分。
- 成績、問答題批改與相關紀錄寫入中央 PostgreSQL／Supabase；本機開發才可使用 SQLite fallback。
- 答案 key 不會在考前／作答中的 learner payload 中暴露。

## 課程與教材建立

教師／管理者主要使用「＋ 建立教學內容」：

- 建立／管理考卷
- 一般考題、圖片判讀題、影片互動題
- AI 輔助出題（候選題仍須教師審核）
- 上傳一般教材／影音教材
- 外部影音／連結
- 顯微鏡／血球 Atlas

Course Wizard 的 canonical frontend owner 是 `static/course-wizard-681.js`；Course Bundle backend 的 canonical owners 是 `teacher_app.courses.bundle_routes` 與 `teacher_app.courses.bundle_followup_routes`。root `course_bundle_72.py` / `course_bundle_followup_73.py` 僅保留 compatibility import seam。`static/system-admin.js` 僅保留 legacy compatibility，不應新增產品邏輯。詳見 `ARCHITECTURE.md`。

## 本機開發

建議 Python 3.12：

```bash
python -m pip install -r requirements.txt
python -m flask --app pgy_app:app run --debug
```

本機若不設定 `DATABASE_URL`，系統會使用 SQLite fallback。要測試正式 PostgreSQL 行為，請使用獨立測試資料庫，不要把 production credentials 寫入 repository。

### 資料庫 migration 與帳號角色維運

正式 Web entrypoint `pgy_app:app` 由 `teacher_app.create_app()` 建立應用；`teacher_app.maintenance.bootstrap` 先建立各 domain 的 pre-migration base schema，再由 `teacher_app.maintenance.migrations` 套用一次性 release migrations。`0064-baseline` 正式擁有 `user_accounts` 基礎表，R2 免費額度保護表由 `0067-r2-free-budget-guard` 建立；啟動流程不再另外重跑 R2 相容 DDL。

帳號角色不會在 Web 啟動時自動變更。若維運人員需要明確授予既有帳號 `system_admin`，使用：

```bash
python -m teacher_app.maintenance.account_roles grant-system-admin USERNAME
```

此命令只更新已存在帳號的角色欄位，不建立帳號，也不修改密碼與個人資料。

## Render 部署必要設定

`render.yaml` 已定義 Web Service 與非敏感預設值。正式環境由
`teacher_app.config.deployment_config_status()` 檢查部署設定；啟動時會記錄
缺項代碼，`/health` 的 `configuration` 區塊也會列出相同警告，但不會回傳
任何 secret 值。`/health` 的 HTTP `200/503` 與頂層 `status` 只由 database 與
migration readiness 決定；`configuration.ok=false` 是部署診斷訊號，不會單獨把
健康檢查改成 `503`。會讓服務無法安全啟動的條件仍由 startup hardening fail-fast；
例如 `PRODUCTION_REQUIRE_SECRET=true` 時，`SECRET_KEY` 少於 32 字元會在 Web
開始服務前直接拒絕啟動。

必填或依功能條件必填的 secrets / connection values 如下，不能提交到 GitHub：

- `DATABASE_URL`：正式 Render 必填，指向持久化 PostgreSQL／Supabase。
- `SECRET_KEY`：正式環境必填且至少 32 字元，不能以 `ADMIN_KEY` 或開發預設值替代。
- `ADMIN_KEY`：僅作為**已登入且具合格 RBAC 權限使用者**執行敏感操作時的短效 elevation/revalidation secret；它不能單獨授權 API，`X-Admin-Key` 也不是 bearer credential。
- `MATERIAL_WORKER_TOKEN`：`MATERIAL_BACKGROUND_JOBS=true` 或啟用 Worker API 時必填。
- `GROQ_API_KEY`：`AI_EXTERNAL_PROCESSING_ENABLED=true` 且 `AI_PROVIDER=groq`／`auto` 時必填。
- `MEGA_EMAIL`、`MEGA_PASSWORD`：選用 MEGA 為 material storage 時必填。
- `R2_ACCOUNT_ID`、`R2_ACCESS_KEY_ID`、`R2_SECRET_ACCESS_KEY`、`R2_BUCKET_NAME`：選用 R2 staging/storage 時必填。
- `GDRIVE_CLIENT_ID`、`GDRIVE_CLIENT_SECRET`、`GDRIVE_REFRESH_TOKEN`、`GDRIVE_FOLDER_ID`：選用 Google Drive 或設定為 storage failover 時必填。

目前登入失敗 rate limiting 是 process-local。正式設定以 `render.yaml` 的
`numInstances: 1` 與 `run_web.sh` 預設 `WEB_CONCURRENCY=1` 為支援拓撲；若未來
改成多 instance 或多 Gunicorn process，必須先加入共享 limiter backend，不能把
目前的 in-memory 計數視為跨 process／跨 instance 限流。

部署後至少確認：

1. `/health` 回傳 `200`、`status=healthy`、database OK、migrations OK，並另外檢查 `configuration.ok` / `configuration.warnings` 是否只包含已知且可接受的條件式警告；不要把 HTTP `200` 誤解為所有條件式 provider 設定都完整。
2. 登入 → `/api/auth/me` → 登出流程正常。
3. 教師可建立課程／教材／考卷／題目，RBAC scope 正確。
4. 學員可開始考試、提交一次並看到正確結果狀態。
5. 教材 job 能被可信 Worker claim、heartbeat、complete；大型檔案 R2 direct upload 正常。
6. Render 實際 `DATABASE_URL` 指向預期的 Supabase PostgreSQL / pooler，且沒有 authentication / connection errors。

## Release Candidate gate

`RC_FEATURE_UI_COVERAGE_MATRIX.md` 是目前 living RC contract。正式提升 RC 前必須滿足：

- 每個 `Usable` 功能都有正常 UI/caller、RBAC 與 regression coverage。
- `Internal` 功能不暴露成一般使用者流程。
- `Compatibility` code 不新增 business logic。
- `Deferred` 項目不宣稱已完成 ownership convergence。
- `Teacher release checks` 必須在 **exact RC commit** 上成功。

GitHub Actions 的 `Teacher release checks` 會執行 Python compile、完整 regression/integration suite、Browser JavaScript syntax、Web/worker shell contracts、migration/health/security contracts，以及 deployment/compatibility policy checks。

## 重要文件

- `RC_FEATURE_UI_COVERAGE_MATRIX.md`：目前 RC 功能與 UI 覆蓋契約
- `ARCHITECTURE.md`：目前 canonical architecture、runtime ownership 與 root freeze policy
- `docs/archive/ARCHITECTURE_HISTORY.md`：6.5 / 6.6 / 6.7 歷史架構與 release contract
- `LOCAL_WORKER_6_7.md`：院內／本機 Worker 設定
- `VERSION` / `release_contract.py`：目前正式 release contract

## GitHub 安全原則

不要提交 `.env`、production database URL、secret key、worker token、R2/MEGA/Google credentials、使用者上傳檔案、暫存轉檔資料或 Python cache。GitHub 用於版本控制；正式執行環境由 Render + PostgreSQL/Supabase + 外部 storage / local worker 組成。
