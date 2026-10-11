# Lighthouse 網頁品質檢測

**目的**：定期檢查網站頁面的**速度**、**無障礙**（視障、色彩對比、鍵盤操作等）與**最佳實務**，及早發現「改版後變慢或變難用」的退步，並留下紀錄。

- 設定：`tests/lighthouse/lighthouserc.js`
- 登入腳本：`tests/lighthouse/login-script.js`
- 結果整理：`tools/lighthouse_summary.py`
- 自動化：`.github/workflows/lighthouse.yml`

## 什麼時候會執行

- **每週一台灣時間 03:37 自動執行**（正式站）。
- 也可以隨時手動執行（見下）。
- 不會隨每次程式更新執行，也不會影響網站上線流程。所有標準都只是「提醒」，**不會讓流程變紅或擋住更新**。

## 手動執行（在 GitHub 網頁上操作）

1. 開啟專案 GitHub 頁面 → 上方 **Actions**。
2. 左側清單點 **Lighthouse performance audit**。
3. 右側點 **Run workflow** → 再點綠色 **Run workflow**（網址欄位留空即可，會檢測正式站）。
4. 等約 5～10 分鐘，重新整理後點進最新那一筆。
5. 左側有兩個項目：`Lighthouse (desktop)`（電腦版）與 `Lighthouse (mobile)`（手機版）。點進去，頁面下方 **Summary** 就是中文結果表。
6. 想看詳細建議：頁面最下方 **Artifacts** 下載 `lighthouse-desktop-…`／`lighthouse-mobile-…`，解壓縮後用瀏覽器開啟 `.report.html` 檔。

## 怎麼看結果

| 欄位 | 意義 | 達標標準（🟢） |
|---|---|---|
| 速度 | 頁面載入與反應整體分數（滿分 100） | 60 分以上 |
| 無障礙 | 是否方便各種使用者操作（滿分 100） | 90 分以上 |
| 最佳實務 | 是否有錯誤訊息、過時寫法等（滿分 100） | 90 分以上 |
| 最大內容顯示 | 主要內容出現要多久 | 4 秒內 |
| 版面位移 | 載入過程畫面是否亂跳 | 0.1 以下 |
| 操作卡頓 | 載入時有多久無法點擊 | 600 毫秒內 |

🟠 代表未達標，只是提醒。看到 🟠 時，建議先看下載報告裡的建議項目，再決定要不要處理。

> **手機版**會模擬較慢的網路與手機效能，因此分數通常比電腦版低，這是正常的。院內同仁多用電腦時，請以電腦版為主要參考。

## 檢測哪些頁面

- **有登入帳號時**（建議）：先登入，再檢測同仁實際看到的頁面，預設為 `/`（首頁）、`/internal`、`/pgy`。
- **沒有登入帳號時**：只檢測 `/login` 與 `/`。首頁在未登入時會因為讀取不到資料而出現錯誤訊息，分數會偏低，不能代表同仁實際體驗。

### 設定登入帳號

與壓力測試共用同一組設定，請見 [LOAD_TEST.md](LOAD_TEST.md) 的「使用壓力測試帳號登入」：優先使用 `TEACHER_LOAD_USERNAME` / `TEACHER_LOAD_PASSWORD`（建議專用學員帳號），沒有時沿用 `TEACHER_SMOKE_USERNAME` / `TEACHER_SMOKE_PASSWORD`。

### 想檢測其他頁面

1. GitHub 專案 → **Settings** → **Secrets and variables** → **Actions** → **Variables** 分頁。
2. 點 **New repository variable**。
3. Name 填 `LIGHTHOUSE_PATHS`。
4. Value 填頁面路徑，用逗號分隔，例如：`/,/internal,/pgy,/system`。
5. 存檔後重新執行。

> 登入帳號沒有權限開啟的頁面會讓該次檢測失敗，請只放該帳號能正常開啟的頁面。

## 在自己電腦執行（進階，選用）

需要已安裝 Node.js 與 Chrome：

```
npm install --no-save @lhci/cli@0.15.1 puppeteer-core@24
npx lhci autorun --config=tests/lighthouse/lighthouserc.js --collect.url=<要檢測的網址>
```

要檢測電腦版請先設定環境變數 `LH_PRESET=desktop`；要先登入請設定 `LH_USERNAME` 與 `LH_PASSWORD`。

## 作為品質紀錄

每次執行的報告保留 30 天。若評鑑或稽核需要留存，請將 Summary 截圖或下載 Artifacts，與當次版本號（`VERSION` 檔）一併歸檔。
