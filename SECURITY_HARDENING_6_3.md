# Teacher 6.3.0 — Exam Integrity & Production Hardening

## 主要變更

- 學員考試改用 `/api/exam-attempts` 建立伺服器端作答快照。
- 作答前不再把 `correct`、`correctIndices`、`acceptedAnswers` 或 `explanation` 下放瀏覽器。
- 分數、答對/答錯題數與合格狀態全部由伺服器計算並直接寫入 `exam_records`。
- 舊 `/api/records` 學員端成績寫入被阻擋，避免自行偽造 score/status。
- PGY 學員送出、教師簽核、組長複核、最終確認、退回與取消改為交易式更新；狀態更新使用 `WHERE id AND status` 防止重複提交與競態。
- 正式站加入登入失敗節流、Same-Origin 寫入檢查、安全標頭、12 小時 Session。
- Render 正式環境要求獨立 `SECRET_KEY`，Cookie 強制 Secure。

## Render 升級前必做

請在 Render Environment 設定一個至少 32 字元、不可公開的 `SECRET_KEY`。可在本機產生：

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

不要把產生值提交到 GitHub。

`CSP_ENFORCE=false` 預設只以 Report-Only 方式觀察既有 CDN/inline script 相容性；確認無阻擋後再改為 `true`。

## 相容性

- 原本教材、課程、題庫、人工問答題批改、PGY 評量、Render/PostgreSQL/MEGA/GDrive 架構保留。
- 6.2 以前瀏覽器 localStorage 的考卷題目草稿不再沿用；第一次進入該考卷時會建立新的安全 attempt。
- 考試作答 attempt 預設 24 小時失效。
