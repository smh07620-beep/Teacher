# 流量提醒（網站自己的用量警示）

**目的**：Render 的 Hobby 工作區每月只有 5 GB 內含流量，用完又沒綁付款方式時，網站會被停用（2026-10-11 發生過）。這個功能讓網站自己統計「送出了多少資料、哪個功能最多」，超過門檻時**寄信**給你，並在系統管理頁顯示本月用量。

## 它統計什麼、不統計什麼

| 會記錄 | 不會記錄 |
|---|---|
| 每天、每個功能類別送出的資料量與次數（例如 `media/uploaded-slides`＝教材投影片圖片、`api/slides`＝教材清單、`static`＝網頁程式與圖示） | 使用者姓名、完整網址、`?` 後面的參數、標頭、內容 |

> **這是估計值。** 它只看得到網站「回應給使用者」的內容，看不到網站自己對外上傳（例如傳到 R2、MEGA）或呼叫 AI 的流量，也不含標頭。**實際用量以 Render 後台為準**，所以提醒門檻要設得比 5 GB 低。

## 設定提醒信箱（只需做一次）

網站已有寄信設定（`SMTP_*`，與帳號 Email 通知共用）。只要再指定「寄給誰」：

1. 開啟 Render 後台 → 選網站服務 → 左側 **Environment** → **Add Environment Variable**。
2. Key 填 `TRAFFIC_ALERT_EMAIL`，Value 填你要收提醒的信箱，儲存。Render 會自動重新部署。
3. 沒設定這一項時，網站仍會統計並在系統管理頁顯示，只是不寄信。

### 調整提醒門檻（選用）

預設在本月統計到 **2.5 GB** 與 **3.5 GB** 時各寄一封（每個門檻每月只寄一次）。以先前 Render 後台的比例推算，網站回應約占實際流量的七成，所以 3.5 GB 約等於 Render 的 5 GB。要改的話新增 `TRAFFIC_ALERT_GB`，例如 `2,3,4`（用逗號分隔）。

## 在哪裡看

登入系統管理者帳號 → **系統管理** → 「教材儲存策略」下方一行：「本月網站已送出約 X GB … 用量最多：…」。

## 關閉

在 Render 後台新增 `TRAFFIC_METER=false`。

## 技術資訊（給維護者）

- 程式：`teacher_app/maintenance/traffic_meter.py`；資料表 `traffic_usage`（日／類別／位元組／次數）與 `traffic_alerts`（已寄出的提醒），由 migration `0119-traffic-meter` 建立（僅新增，SQLite 與 PostgreSQL 皆可）。
- 權限：`GET /api/admin/traffic-usage` 需要 `storage.manage`（系統管理者）。
- 每 60 秒把記憶體中的計數批次寫入資料庫；寫入或寄信失敗只記錄警告，不影響網頁回應。寄信失敗會在 15 分鐘後重試，成功才標記為已寄。
- 環境變數：`TRAFFIC_METER`、`TRAFFIC_ALERT_GB`、`TRAFFIC_ALERT_EMAIL`、`SMTP_*`。
