# 免費額度與流量預算（2026-10-12）

網站完全建立在免費方案上。下表是各項額度、用量來源，以及程式裡已有的控制。每週到後台看一次，超標前先處理。

| 服務 | 免費額度 | 主要用量來源 | 已有的控制 |
|---|---|---|---|
| Supabase（資料庫） | 每月 5 GB 對外流量（整個組織合計） | 使用者請求的查詢；Worker 輪詢的資料庫讀取 | Worker 心跳只讀自己那一筆並定期清理舊紀錄；領工作時的清理最多每 5 分鐘一次（`MATERIAL_CLEANUP_INTERVAL_SECONDS`）；教材清單短快取（`MATERIAL_LIST_CACHE_SECONDS`，Render 設 10 秒） |
| Render（網站） | 每月 5 GB 對外頻寬、750 小時實例時數、500 分鐘建置 | 教材檔案若經 Render 轉送；Worker 輪詢的小回應；GitHub 排程對網站的檢查 | 教材主要儲存為 R2（簽名連結直接送給使用者，不經 Render）；Worker 閒置時放慢輪詢（`MATERIAL_WORKER_IDLE_POLL_MAX_SECONDS`、`AI_QUESTION_WORKER_IDLE_POLL_MAX_SECONDS`，預設 45 秒；有工作時立刻回到 2 秒，所以閒置時上傳或 AI 工作最多晚約 45 秒開始）；夜間靜音（`TEACHER_QUIET_HOURS`，預設 01:00-06:00 台灣時間，設為 `off` 關閉）；網站檢查每小時一次、備援 Worker 每 30 分鐘一次，夜間跳過 |
| Cloudflare R2 | 每月 10 GB 儲存 | 教材檔案與投影片圖片 | `R2_*` 用量門檻與警示（見 `render.yaml`） |
| GitHub Actions | 公開儲存庫的標準主機不計分鐘 | 各排程與測試 | 排程頻率已降低 |

## 夜間靜音

- 時段：每天 01:00–06:00（台灣時間，UTC+8）。院內兩個 Worker 不輪詢、不送心跳，Render 閒置 15 分鐘後休眠，每月可省約 150 小時。
- 閱讀教材不受影響；夜間第一位進站的人需等約 1 分鐘讓網站醒來。
- 這段時間不處理上傳轉檔與 AI 工作；管理員畫面會顯示 Worker 離線，但**不會寄離線警報信**（時段結束後再多等 15 分鐘才恢復警報）。
- 修改或關閉：Worker 所在電腦的環境變數 `TEACHER_QUIET_HOURS`（格式 `HH:MM-HH:MM`，`off` 為關閉）；GitHub 警報排程在 `.github/workflows/worker-offline-alerts.yml`。

## 每週檢查（約 5 分鐘）

1. Render → 工作區 → Billing → Monthly Included Usage：實例時數（上限 750）、對外頻寬（上限 5 GB）。
2. Supabase → 組織 → Usage → Egress：目標每天不超過約 150 MB。
3. 系統管理 → 「教材儲存策略」下方「用量最多」：看 `static`、`media/uploaded-slides`、`api/ai-worker` 各多大。`static` 突然變大多半是新圖片太大；`media/uploaded-slides` 只是導向 R2 的連結，每頁約 1 KB。
4. Render → 網站服務 → Metrics → Outbound Bandwidth：紫線（Service-Initiated，網站自己對外送出）應穩定在每小時約 1 MB 以下（2026-10-13 放寬閒置輪詢前約為 1.3 MB）；綠線（HTTP Responses）的尖峰要能對應到上班時間的使用。
5. 任何一項超過 60% 就先處理，不要等通知信。

## 絕對不要讓教材改走 Google Drive／MEGA

R2 用量到 80% 時，`STORAGE_FAILOVER_ON_FULL` 會把新上傳自動切到備援（Google Drive），之後學員讀這些教材時整份檔案都會經過 Render 的 5 GB 額度。R2 接近滿之前請先清理或處理，不要放任自動切換。
