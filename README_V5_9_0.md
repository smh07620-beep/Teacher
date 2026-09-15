# V5.9.0 — 第二階段前端模組化

本版完成架構整頓計畫的第二階段，網址、資料格式與既有 API 均維持相容。

## 主要變更

- `system.html` 不再內嵌大型樣式與程式，頁面體積由約 433 KB 降至約 97 KB。
- 新增 `shared-core.js`，集中組別設定、學習網址、API 請求、登入身分與個人資料記憶鍵值。
- 功能拆成 `system-core.js`、`system-learner.js`、`system-exam.js`、`system-assessment.js`、`system-admin.js`、`system-bootstrap.js`。
- 登入程式獨立為 `login.js`，並透過共用 API 層送出請求。
- 歷代樣式依用途整併成 `design-tokens.css`、`portal.css`、`learner.css`、`admin.css`。
- 舊版 CSS 檔保留作相容參考，但主要頁面不再逐一載入多代覆寫檔。

## 維護方式

- 首頁、院內訓練與 PGY 入口：修改 `portal.css` 與 `portal-v56.js`。
- 組內教材、閱讀器與個人進度：修改 `learner.css`、`system-learner.js`。
- 考卷與答題：修改 `system-exam.js`。
- PGY 評量：修改 `system-assessment.js`。
- 後台：修改 `admin.css`、`system-admin.js`。
- 共用組別或 API 行為：修改 `shared-core.js`。

## 驗證

- JavaScript 語法檢查全數通過。
- 既有 Node 合約測試與 Python 後端測試全數通過。
- 第二階段新增模組邊界測試，避免大型內嵌程式重新回到 HTML。
