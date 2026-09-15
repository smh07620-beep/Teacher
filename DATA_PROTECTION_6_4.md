# Teacher 6.4.0 — Data Protection & Recovery

6.4 延續 6.3 的伺服器計分、PGY 原子簽核與正式站安全設定，新增四個維運層級能力。

## 1. 邏輯備份與保守還原

系統管理者與教學管理者可從 `/system` 下載 Teacher 邏輯備份 ZIP。備份包含主要資料表 JSON 快照與 SHA256 摘要。還原採 **insert-missing-only**：不清空、不覆蓋現有正式資料，適合事故後補資料或轉移環境前驗證。

> 這不是 PostgreSQL provider snapshot 的替代品。正式環境仍建議保留 Render/Supabase/雲端資料庫本身的定期備份。

## 2. Schema migration baseline

新增 `schema_migrations` 表與 `0064-baseline`。既有 `app.py` 的 legacy init 邏輯仍保留，6.4 起新增 schema 應改由 migration registry 管理，避免未來版本無法判斷資料庫已套用哪些變更。

## 3. 上傳檔案驗證

所有 multipart POST/PUT/PATCH 在進入舊處理器前會做內容簽章檢查：PDF、PNG/JPEG/GIF/WebP、Office ZIP/OLE、常見影音；ZIP/OOXML 另檢查檔案數、展開後大小、壓縮比與路徑穿越，降低副檔名偽裝與 ZIP bomb 風險。

Render 可調整：

- `UPLOAD_ZIP_MAX_FILES=2000`
- `UPLOAD_ZIP_MAX_EXPANDED_MB=1024`
- `UPLOAD_ZIP_MAX_RATIO=200`

## 4. AI 去識別與外部處理開關

新增：

- `AI_EXTERNAL_PROCESSING_ENABLED=true`
- `AI_DEIDENTIFICATION_ENABLED=true`
- `AI_EXTERNAL_MEDIA_ALLOWED=false`

文字教材在送往外部 AI 前會遮罩常見姓名、病歷號、身分證號、電話、手機與生日格式。6.4 預設禁止把圖片、影片、音訊原檔直接送往外部 AI；院方若完成政策審核後，可再明確開啟。

> 自動去識別只能降低風險，不能保證所有敏感資訊都能被偵測。教材上傳與 AI 使用仍應遵守院內病人資料與資訊安全規範。

## 部署

6.3 的 `SECRET_KEY`、`SESSION_COOKIE_SECURE=true` 等設定仍為必要條件。升級 6.4 不需要清空或重建資料庫。
