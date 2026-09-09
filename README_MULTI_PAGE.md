# 檢驗科教學網｜多頁面教育訓練版

此版本由原有 Flask 教育訓練/考核系統擴充而來，原有生化組固定教材與考題邏輯保留在「內部教育訓練區」。

## 網站入口
- `/`：教學網首頁
- `/internal`：內部教育訓練區 → 六組
- `/pgy`：PGY 訓練區 → 六組
- `/system?area=internal&group=grpBio`：實際教材/考試系統

六組：生化、鏡檢、血清、血庫、細菌、血液。

## 新增功能

### V6.1.0 第四階段：身分權限第一批

- 管理者帳號登入後可直接操作管理 API；`ADMIN_KEY` 僅保留為初始化與緊急救援入口。
- PGY 評核僅允許臨床教師與教學管理者建立，評估者姓名及職稱由登入帳號綁定。
- 臨床教師僅能建立及查看自己負責組別的評核；學員僅能查看自己的紀錄。
- 首頁院內／PGY 切換不要求登入，點入教材、考試或評核內容時才進入登入流程。

### V6.1.0 第四階段：身分權限第一批

- 管理者帳號登入後可直接操作管理 API；`ADMIN_KEY` 僅保留為初始化與緊急救援入口。
- PGY 評核僅允許臨床教師與教學管理者建立，評估者姓名及職稱由登入帳號綁定。
- 臨床教師僅能建立及查看自己負責組別的評核；學員僅能查看自己的紀錄。
- 首頁院內／PGY 切換不要求登入，點入教材、考試或評核內容時才進入登入流程。
1. 第三階段首頁改為醫學檢驗學習儀表板：保留主視覺、四項學習摘要、六大組別與最新教材／待完成考核。
2. PGY 採分散式學習層級：6 大核心能力 → 訓練階段 → 訓練領域 → 學習項目 → 教材 → 測驗／技能評核 → 教師評核 → 完成狀態 → 學習證據 → 學員回饋 → 教師簽核。
3. PGY 評核方式依正式代碼分為 EXAM、DOPS、MINI-CEX、CBD、CHECKLIST、QC、360、REPORT、QI、REFLECTION、ATTENDANCE；舊評量代碼僅保留資料相容性。
4. 內部教育與 PGY 分流，教材與動態題庫依 training_area 區隔。
5. 每區皆有六組入口，每組內含教材區與考試區。
6. 問答題 (`questionType=essay`) 顯示多行空白欄，考生可輸入自由文字；答案保存於成績明細，問答題不納入選擇題自動計分，供評核者人工閱卷。
7. 教材支援：PPT/PPTX、PDF、Word、Excel、ODP/ODT/ODS、圖片、MP4/WebM/MOV、MP3/WAV/M4A、TXT/CSV/ZIP 等。
   - PPT/PDF/Office 文件：可轉成逐頁圖片瀏覽（Office 轉檔需 LibreOffice）。
   - 圖片/影音：瀏覽器直接開啟原檔。
8. 題庫可由公開 HTTP/HTTPS JSON 或 CSV 連結批次匯入；後端會阻擋 localhost、私有 IP、保留 IP，並限制下載大小。
9. 原有 PostgreSQL / SQLite、Render Persistent Disk、成績後台與 Word 匯出功能保留。

## 題庫連結格式
CSV 可使用欄位：
`question,questionType,optionA,optionB,optionC,optionD,correct,tag,explanation,imageUrl`

- `questionType`: `choice` 或 `essay`
- `correct`: 可填 `0/1/2/3` 或 `A/B/C/D`
- 問答題的選項與 correct 可留空。

JSON 可直接是一個陣列，或 `{ "questions": [...] }`；每題欄位與 CSV 類似，也可直接提供 `options: ["A...", "B..."]`。

## Render 建議
- `ADMIN_KEY`：請在 Render Environment 設定，不要使用程式內預設值作正式密碼。
- `DATABASE_URL`：接 PostgreSQL 時設定。
- `MATERIAL_STORAGE=/var/data/materials`，並掛載 Persistent Disk 至 `/var/data`，避免上傳教材在重部署後消失。
- Dockerfile 需保留 LibreOffice，才能讓 PPT/Word/Excel 自動轉 PDF/圖片。

## 注意
外部題庫連結功能目前支援公開 JSON / CSV。Google Sheets 建議使用「發布到網路」後的 CSV 下載網址；需要登入權限的 Google Drive、SharePoint 或院內網路網址不會自動抓取。
