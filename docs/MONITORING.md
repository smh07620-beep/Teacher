# 監控與通知總覽

這份文件說明：網站目前有哪些自動檢查、出事時誰會收到通知，以及兩項可選的補強（程式錯誤通知、外部網站偵測）怎麼啟用。

## 一、目前已有的檢查

| 項目 | 頻率 | 檢查什麼 | 對應檔案 |
|---|---|---|---|
| 線上驗收（production smoke） | 每 15 分鐘 | 網站版本是否正確、`/health` `/ready` `/live`、首頁與登入頁、未登入時受保護頁面是否確實擋住；有監控帳號時另外確認院內 Worker 在線且版本最新 | `.github/workflows/production-smoke.yml` |
| 完整流程檢查（synthetic） | 每天 1 次 | 網站 → 資料庫 → 雲端儲存 → 院內 Worker 整條鏈是否真的連通，並自動清除測試資料 | `.github/workflows/production-synthetic.yml` |
| Worker 離線／異常通知 | 每 10 分鐘 | Worker 離線或錯誤過多時**寄 Email** 通知 | `.github/workflows/worker-offline-alerts.yml` |
| 資料庫保活 | 每天 1 次 | 喚醒網站並確認 Supabase 資料庫可連線 | `.github/workflows/supabase-keepalive.yml` |

本次新增：

| 項目 | 頻率 | 說明 |
|---|---|---|
| 壓力測試 | 手動 | [LOAD_TEST.md](LOAD_TEST.md) |
| Lighthouse 網頁品質檢測 | 每週＋手動 | [LIGHTHOUSE.md](LIGHTHOUSE.md) |
| 程式錯誤通知（Sentry） | 啟用後即時 | 見第三節，**預設關閉** |
| 流量提醒（Render 流量用量） | 即時統計，達門檻寄信 | [TRAFFIC_METER.md](TRAFFIC_METER.md)；需設定 `TRAFFIC_ALERT_EMAIL` |
| 儲存明細（MEGA／R2 每一筆紀錄） | 系統管理 → 教材儲存策略 → 「查看儲存明細」；只讀列出含旁白音檔、孤兒紀錄、停用、未歸課程，可逐筆刪除（走既有教材刪除 API 與稽核） | `GET /api/admin/storage/rows`（需 `storage.manage`）；程式 `teacher_app/storage/row_audit.py` |

> 上述自動檢查若失敗，是以 GitHub Actions 的失敗通知呈現（通常寄給排程檔最近一次的修改者）。請確認該 GitHub 帳號的通知設定有開啟 Actions 通知。目前**只有 Worker 異常會另外寄 Email**；網站本身掛掉時，沒有獨立於 GitHub 的即時通知，這是第二節要補的缺口。

## 二、建議補強：外部網站偵測（Uptime Kuma）

### 為什麼需要

1. **網站掛掉時要即時知道。** 目前每 15 分鐘的檢查依賴 GitHub 排程，排程可能延遲，通知也不是即時的。
2. **Render 免費方案閒置 15 分鐘就會休眠，下次有人開網站要等約 1 分鐘重新啟動。** 上線初期同仁陸續登入時，第一位使用者會遇到這個等待。每 5 分鐘有一次偵測，可以讓上班時段維持喚醒。
3. **流量上限**：Render Hobby 工作區每月有免費流量上限，用完網站會被自動停用（2026-10-11 發生過）。偵測請求很小，但教材、影音若經由 Render 傳送會快速累積；請定期到 Render 後台查看用量。
4. 注意事項（依 [Render 官方說明](https://render.com/docs/free)）：每個 workspace 每月有 750 小時免費時數；服務一整個月都維持喚醒時約用掉 720～744 小時（一個月的總時數），所以**同一個 workspace 不要再放其他免費服務**；用完時數所有免費服務會被停用到下個月。建議只在上班時段偵測，或到 Render 後台確認時數用量。

### 要監控的項目

| 名稱 | 網址 | 間隔 | 判斷 |
|---|---|---|---|
| Teacher 存活 | `https://<正式站網址>/live` | 5 分鐘 | HTTP 200，內容含 `"status":"live"` |
| Teacher 就緒 | `https://<正式站網址>/ready` | 15 分鐘 | HTTP 200，內容含 `"status":"ready"`（會檢查資料庫與必要設定） |

> `/live` 不查資料庫，負擔最小，適合頻繁偵測；`/ready` 會連資料庫，間隔拉長即可。

### 在哪裡執行

Uptime Kuma 是開源軟體，需要一台**不關機、能安裝 Docker** 的電腦或伺服器。院內 Worker 電腦雖然不關機，但它已有專門用途並以系統工作排程管理，不建議混用。

安裝方式請以官方說明為準（[GitHub 專案頁](https://github.com/louislam/uptime-kuma)）。常見做法是用 Docker 執行，預設使用 3001 連接埠，資料保存在 `/app/data`。

> **我沒能在這個環境實際安裝測試 Uptime Kuma**（這裡沒有 Docker 服務），所以沒有附上現成的安裝檔，以免提供未驗證的內容。若院內沒有合適的電腦，請告訴我，我們再評估其他方式；若改用雲端偵測服務，使用前請先確認其免費方案的使用條款是否允許醫院使用。

### 通知設定

在 Uptime Kuma 的通知設定中新增 **Email (SMTP)**。網站本身已經使用 Gmail SMTP 寄信（見 `render.yaml` 的 `SMTP_*` 設定），可以沿用同一組寄信帳號。

## 三、建議補強：程式錯誤通知（Sentry）

### 它補了什麼

網站發生**沒被處理的伺服器錯誤（HTTP 500）**時，Sentry 會收到錯誤種類、錯誤訊息與出錯位置，並寄通知，讓你不必翻 Render 的記錄才發現。

### 預設關閉，且只送最少資料

只有設定了 `SENTRY_DSN` 才會啟用，沒設定就完全不動作（程式在 `teacher_app/maintenance/error_reporting.py`）。

| 會送出 | **不會**送出 |
|---|---|
| 錯誤種類、錯誤訊息、出錯程式位置 | Cookie、登入帳號、請求標頭 |
| 版本與部署編號 | 請求內容（教材、考試作答、評核資料） |
| 出錯的網頁路徑（不含 `?` 後面的參數） | 網址參數、IP 位址、區域變數、操作軌跡 |

已用自動測試驗證：密碼、Cookie、網址參數、作答內容都不會出現在送出的資料裡（`tests/test_error_reporting_20261011.py`）。

> 「錯誤訊息」文字仍會送出。專案的記錄規範本來就禁止在錯誤訊息中放個資與金鑰（見 [ERROR_OBSERVABILITY_CLOSEOUT.md](ERROR_OBSERVABILITY_CLOSEOUT.md)）。**啟用前，建議先依院內資訊安全規定確認可使用此外部服務**（此為資料送出院外的項目）。

### 啟用步驟

1. 到 [Sentry 官網](https://sentry.io) 註冊並建立專案，平台選 **Flask**。建立完成會給一串 **DSN**，長得像 `https://xxxx@xxxx.ingest.sentry.io/123456`。
2. 開啟 Render 後台 → 選網站服務 → 左側 **Environment** → **Add Environment Variable**。
3. Key 填 `SENTRY_DSN`，Value 貼上剛才的 DSN，儲存。Render 會自動重新部署。
4. 部署完成後，到服務的 **Logs** 搜尋 `sentry_enabled`。看到這行就代表已啟用；沒有看到代表沒設定成功。
5. （選用）在 Sentry 專案設定通知對象與 Email。

要確認 Sentry 真的收得到，可以送一筆測試訊息（需有 Python 環境，不熟悉的話請找我協助）：

```
SENTRY_DSN="你的DSN" python tools/sentry_test_event.py
```

### 關閉

在 Render 後台把 `SENTRY_DSN` 刪除或清空並儲存即可。

### 範圍

只涵蓋網站（Render 上的 Web 服務）。院內的 Material Worker、AI Worker 不在內，它們仍由原有的離線通知處理。

## 四、作為評鑑佐證

- 每次自動檢查的結果都留在 GitHub Actions 紀錄中（Artifacts 保留 14～30 天）。
- 若評鑑需要，可截圖 Actions 頁面的近期執行紀錄，並與當次版本號（`VERSION` 檔）一併歸檔。
- 變更紀錄（誰在何時改了什麼）由 GitHub 的提交紀錄保存。
