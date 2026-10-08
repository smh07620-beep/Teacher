# 講稿自動對應投影片（講者備註）— 2026-10-08

目標：老師不必自己找切點。

## 行為
- **產生 PowerPoint 時自動套用**：同一份教材若已有「已核准講稿」，且所有啟用的投影片都還沒有講者備註，
  `ai_presentation_runtime.generate_presentation` 會呼叫 `script_alignment.attach_script_notes`，
  把講稿依內容分段填入每頁備註（寫進第 1 版 revision 與 PPTX speaker notes）。
  老師已手寫的備註不會被覆蓋；沒有已核准講稿、或自動分段出錯時，產檔照常，備註維持空白。
- **AI 影片**照原本規則逐頁念備註；備註為空時念標題與重點。
- **編輯器**「教師投影片編輯器」多了「依內容自動分段」：預設選最新的已核准講稿，按一次即可重新分段（預覽，
  儲存仍走既有 `PATCH /api/ai-presentations/<id>`，建立新 revision）。每頁顯示預估念稿時間。

## 切點怎麼找（`teacher_app/materials/script_alignment.py`）
1. 講稿先依空行切成段落；段落不夠再依換行、再依句號切；結尾的「※ 需由授課教師確認」不當旁白。
2. 以「相鄰字雙連詞」比對每段與每頁（標題＋重點＋區塊文字）的相似度，常見詞降權。
3. 動態規劃：維持講稿原順序，把連續段落分給各頁，總相似度最高；加上輕微字數平衡，避免一頁吞掉全部。
4. 段落比頁數少時一段對一頁，其餘頁留空；單頁備註上限 4000 字。
不呼叫 AI，結果固定、免費、可在 Web request 內完成。

## 講稿長度與語速
講稿提示詞要求依目標分鐘數產生，換算為「每分鐘約 280 字」的正常語速，並要求用空行把講稿分成每段
約 150–350 字、一段一個教學重點（`media_script_runtime._draft_instruction`）。這是對 AI 的要求，不是事後強制；
編輯器會顯示每頁實際字數與預估秒數，AI 影片完成後的時間軸則是實際語音長度。

## 新增 API
`POST /api/ai-presentations/align-script`：body `{scriptId, slides:[{id,title,bullets,blocks}]}`，
需 `presentation.edit` 與講稿所屬組別範圍；只回傳預覽，不寫入任何資料。

## 優化（同日）
- **逐張寫講稿**：同一份教材若已有「已核准的投影片大綱」，產生講稿時會自動把大綱附進提示詞，要求「剛好 N 段、第 k 段對應第 k 張」
  （`media_script_jobs._approved_slide_outline`、`media_script_runtime._outline_rule`）。段落數若與張數不同，後面的自動對應仍會處理。
  建議流程：先核准投影片大綱，再產生講稿。
- **長度檢查**：講稿比目標長超過 25% 時，**只在使用雲端 AI 時**請 AI 縮短一次，並保留較接近目標的版本；本機模型（Ollama）不重試，
  太短也不補（避免為湊長度編造內容）。重試失敗時保留第一版。結果會記錄 `estimatedMinutes`、`lengthRetried`、`slideOutlineCount`。
- **額度**：以上不增加每次產生的 AI 呼叫次數，只有「過長」時多一次；自動分段不呼叫 AI。免費 AI 備援順序仍是 Groq → Gemini → 本機 Ollama。
- **畫面**：講稿編輯區顯示預估念稿時間；投影片編輯器開啟時，若所有備註都是空的且有已核准講稿，會自動預填（需按儲存才生效）。
- **尚未做**：字面相似度很低時改請 AI 判斷切點；瀏覽器端到端（Playwright）測試。
