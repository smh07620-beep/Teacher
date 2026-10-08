# Worker 自動更新，以及在另一台電腦新增一個相同的 Worker

這份文件給「不太熟程式」的管理者：每一步都寫明要開哪個視窗、貼哪一行。

## 一、運作方式（先看這段就好）

- 教材 Worker 和 AI Worker 放在**同一個程式資料夾**，所以只要更新這一個資料夾就行。
- **教材 Worker** 每隔一段時間（預設 6 小時，下面設成 1 小時）檢查 GitHub 上名為 `worker-stable` 的「核准標籤」。標籤往前移動了，就更新程式資料夾，然後自己重新啟動。
- **AI Worker** 不自己跑任何 git 指令。它每分鐘看一次程式資料夾的版本，發現被更新了，會在**沒有工作在跑的時候**自己重新啟動，載入新版。
- Worker 不會自己追蹤 `main`。要讓新程式到 Worker，必須有人把 `worker-stable` 標籤移到想發布的版本（見第四節）。這道關卡是刻意保留的：Worker 在院內，不應該一有人改 `main` 就自動執行。

## 二、第一次設定（要在放 Worker 的那台電腦做一次）

目前那台電腦的 Worker 版本太舊，還沒有自動更新的功能，所以第一次必須手動更新。

**開始之前，要先有 `worker-stable` 這個標籤。** 標籤只能由有權限的人建立（Claude 的工作階段沒有權限）。在你的開發電腦的 PowerShell 做第四節那三行，或到 GitHub 專案頁：右側點「Releases」→「Create a new release」→ 在「Choose a tag」輸入 `worker-stable` 並選「Create new tag」→ 目標選 `main` → 按「Publish release」。

1. 在放 Worker 的那台電腦按 Windows 鍵，輸入 `PowerShell`，對「Windows PowerShell」按右鍵，選「以系統管理員身分執行」。
2. 進入 Worker 資料夾（以實際位置為準，下面以 `C:\TeacherWorker` 為例），然後貼上這幾行，一行一行按 Enter：

```powershell
cd C:\TeacherWorker
git checkout main
git pull --ff-only origin main
git fetch origin tag worker-stable
```

   如果 `git pull` 說有檔案被修改（dirty），先不要硬做，把畫面貼給開發者。
3. 用記事本打開 `C:\TeacherWorker\.local-worker.env`，找到下面這幾行，改成這樣（找不到就加在最後面）：

```text
MATERIAL_WORKER_AUTO_UPDATE=true
MATERIAL_WORKER_UPDATE_INTERVAL_HOURS=1
MATERIAL_WORKER_RELEASE_REF=worker-stable
MATERIAL_WORKER_REQUIRE_SIGNED_TAG=false
AI_WORKER_RESTART_ON_UPDATE=true
```

   `MATERIAL_WORKER_REQUIRE_SIGNED_TAG=false` 表示不要求標籤有數位簽章。它的保護比預設弱，只因為目前沒有簽章流程才這樣設；有簽章流程後請改回 `true`。
4. 存檔後，重新啟動兩個工作排程：按 Windows 鍵輸入「工作排程器」並開啟，左邊點「工作排程器程式庫」，在清單找到 `Teacher Material Worker` 和 `Teacher AI Worker`，各按右鍵選「結束」，再按右鍵選「執行」。
5. 打開網站的 Worker 狀態頁，確認兩個 Worker 都在線，而且 Git SHA 與網站一致。

## 三、在另一台電腦新增一個相同的 Worker

**不要用聊天、Email 傳 `.local-worker.env`。** 這個檔案裡有 Worker 密碼、資料庫與儲存空間的金鑰，請用隨身碟或院內的安全方式複製。

1. 在新電腦安裝兩個軟體（都用預設選項一路按「下一步」）：
   - Git for Windows：<https://git-scm.com/download/win>
   - Python 3.12：<https://www.python.org/downloads/windows/>，安裝畫面第一頁要勾選「Add python.exe to PATH」。
2. 按 Windows 鍵，輸入 `PowerShell`，對「Windows PowerShell」按右鍵，選「以系統管理員身分執行」。
3. 貼上這兩行，一行一行按 Enter（網址若跳出 GitHub 登入視窗，用原本的帳號登入）：

```powershell
cd C:\
git clone https://github.com/smh07620-beep/Teacher.git C:\TeacherWorker
```

4. 把舊電腦的 `.local-worker.env` 複製到新電腦的 `C:\TeacherWorker\` 資料夾。
5. 用記事本打開新電腦上的這個檔案，找到 `MATERIAL_WORKER_ID=` 那一行，**把等號後面的內容刪掉**（留空），或改成這台電腦專屬的名字，例如 `lab-pc-2`。兩台電腦用同一個名字，網站會以為是同一個 Worker，彼此蓋掉狀態。存檔。
6. 回到 PowerShell，貼上下面這幾行：

```powershell
cd C:\TeacherWorker
powershell -ExecutionPolicy Bypass -File .\setup_teacher_worker.ps1 -InstallOptionalTools -InstallTasks -SkipReleaseUpdate -StartNow
```

   - 過程中會問你這台電腦的 Windows 登入密碼，這是給「工作排程器」用的，不會寫進檔案。
   - 第一次會下載安裝 FFmpeg、LibreOffice 和語音相關套件，要等一陣子。
7. 完成後，到網站的 Worker 狀態頁，應該會看到新的 Worker 出現並在線。也可以在新電腦執行 `.venv\Scripts\python.exe worker_doctor.py --quick` 做連線自我檢查。

### 兩台電腦同時跑的注意事項

- 工作會被兩台自動分攤，不需要額外設定。
- **AI 語音是否可用，網站只看「最近一次回報的 AI Worker」。** 如果新電腦的 Kokoro（語音）還沒安裝好或還在載入，網站可能在兩台之間來回判斷，語音警告會時有時無。新電腦第一次啟動後，請等 Worker 狀態頁的 AI Worker 顯示 Kokoro 綠燈，再讓它正式接工作。
- 新電腦的 `.local-worker.env` 也要設好第二節第 3 步的自動更新設定，才會跟著自動更新。
- 兩台電腦要保持開機，並且不要睡眠，Worker 才會持續接工作。

## 四、發布新版給 Worker（把標籤往前移）

每次想讓 Worker 用到最新的 `main`，在開發電腦執行下面三行（會把標籤移到 `main` 目前的最新版本）：

```powershell
git fetch origin main
git tag -f -a worker-stable -m "Worker release" origin/main
git push -f origin worker-stable
```

之後最多 1 小時（第二節設定的檢查間隔），教材 Worker 就會更新並重新啟動，AI Worker 約 1 分鐘內跟著重新啟動。也可以直接請 Claude「發布 Worker」代為執行。

## 五、出問題時

| 現象 | 原因與處理 |
|---|---|
| 一直沒有更新 | 檢查 `.local-worker.env` 是否有 `MATERIAL_WORKER_AUTO_UPDATE=true` 和 `MATERIAL_WORKER_RELEASE_REF=worker-stable`；程式資料夾有被手動修改過（dirty）時更新器會拒絕。 |
| 更新後 AI 語音還是「暫時不可用」 | 網站頁面會顯示具體原因，照那一行處理；多半是 AI Worker 還沒重新啟動。 |
| 想暫停自動更新 | 把 `MATERIAL_WORKER_AUTO_UPDATE` 改成 `false`，AI Worker 設 `AI_WORKER_RESTART_ON_UPDATE=false`，再重新啟動兩個排程。 |
