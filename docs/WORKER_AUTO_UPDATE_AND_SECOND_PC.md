# Worker 自動更新，以及在另一台電腦新增一個相同的 Worker

這份文件給「不太熟程式」的管理者：每一步都寫明要開哪個視窗、貼哪一行。

## 一、運作方式（先看這段就好）

- 教材 Worker 和 AI Worker 放在**同一個程式資料夾**，所以只要更新這一個資料夾就行。
- **教材 Worker** 每隔一段時間（預設 6 小時，下面設成 1 小時）檢查 GitHub 上名為 `worker-stable` 的「核准標籤」。標籤往前移動了，就更新程式資料夾，然後自己重新啟動。
- **AI Worker** 不自己跑任何 git 指令。它每分鐘看一次程式資料夾的版本，發現被更新了，會在**沒有工作在跑的時候**自己重新啟動，載入新版。
- Worker 不會自己追蹤 `main`。要讓新程式到 Worker，必須有人把 `worker-stable` 標籤移到想發布的版本（見第四節）。這道關卡是刻意保留的：Worker 在院內，不應該一有人改 `main` 就自動執行。

## 二、第一次設定（要在放 Worker 的那台電腦做一次）

目前那台電腦的 Worker 版本太舊，還沒有自動更新的功能，所以第一次必須手動更新。

**開始之前，要先有 `worker-stable` 這個標籤，而且必須是「註解標籤」。** 不要從 GitHub 的 Releases 頁面建立，那樣建出來的是輕量標籤，更新器會拒絕（錯誤訊息：release ref must be an annotated tag）。請照第四節按一下「Release Worker」按鈕建立。

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

每次想讓 Worker 用到最新的 `main`，在 GitHub 網頁按一個按鈕：

1. 打開專案頁，上方點「Actions」。
2. 左邊清單點「Release Worker (move worker-stable tag)」。
3. 右邊點「Run workflow」，確認分支是 `main`，再按綠色的「Run workflow」。
4. 約 10 到 20 秒後出現綠色勾勾，就表示 `worker-stable` 標籤已移到 `main` 目前的最新版本。

之後最多 1 小時（第二節設定的檢查間隔），教材 Worker 就會更新並重新啟動，AI Worker 約 1 分鐘內跟著重新啟動。

如果之前已經從 Releases 頁面建立過 `worker-stable`，按上面的按鈕會直接把它換成註解標籤，不用先刪除。想整理的話，可以把 Releases 頁面上那筆 `worker-stable` 的 Release 刪掉（只刪 Release，不要刪標籤）。

（熟悉指令的人也可以在有 git 的電腦執行：`git fetch origin main`、`git tag -f -a worker-stable -m "Worker release" origin/main`、`git push -f origin worker-stable`。）

## 五、出問題時

| 現象 | 原因與處理 |
|---|---|
| 一直沒有更新 | 檢查 `.local-worker.env` 是否有 `MATERIAL_WORKER_AUTO_UPDATE=true` 和 `MATERIAL_WORKER_RELEASE_REF=worker-stable`；程式資料夾有被手動修改過（dirty）時更新器會拒絕。 |
| 更新後 AI 語音還是「暫時不可用」 | 網站頁面會顯示具體原因，照那一行處理；多半是 AI Worker 還沒重新啟動。 |
| 想暫停自動更新 | 把 `MATERIAL_WORKER_AUTO_UPDATE` 改成 `false`，AI Worker 設 `AI_WORKER_RESTART_ON_UPDATE=false`，再重新啟動兩個排程。 |

## 六、重要註記：網站什麼時候會擋 AI Worker（2026-10-08 修改）

**這是刻意放寬過的規則，請勿忘記。**

- 原本：網站（Render）與 AI Worker 的 Git commit 只要不同，就把 Worker 視為離線，擋掉 AI 講稿與 Kokoro 語音（診斷代碼 `worker_code_mismatch`）。
- 問題：Render 每次 main 有新推送就自動部署，但 Worker 只跟 `worker-stable` 標籤，所以每次小改動都會出現空窗期，無法測試。
- 現在：
  - commit 不同、但 `VERSION` 檔相同 → **不擋**，只顯示提醒（診斷代碼 `worker_code_behind`，`codeIdentityMatch` 仍為 false）。
  - `VERSION` 不同 → **仍然擋**（`worker_code_mismatch`）。
  - 其他檢查完全不變：heartbeat 超過 120 秒、heartbeat contract < 4 或沒有 workerSha（`worker_build_unknown`）、缺少 media_audio 佇列、Kokoro 不可用，都仍會擋。
- 程式位置：`teacher_app/materials/media_audio_routes.py` 的 `_evaluate_ai_worker`；測試：`tests/test_ai_worker_small_drift_20261008.py`。
- **什麼時候要自己更新 Worker**：改了 `VERSION`；或改動影響網站與 Worker 之間的資料格式（API、佇列、heartbeat）。做法：Actions → Release Worker，再依第二、四節更新 Worker。
- 若要恢復嚴格比對，把該段 `elif` 的 `and _web_version() and worker_version and worker_version != _web_version()` 條件拿掉即可，並更新上述測試。

## 七、重要註記：Worker 用 SYSTEM 帳號時的 MEGAcmd（2026-10-08）

**現象**：AI 講稿失敗，訊息「MEGA 尚未完成設定」或「MEGAcmd Server not running … Unable to execute: C:\Windows\system32\config\systemprofile\AppData\Local\MEGAcmd\MEGAcmdServer.exe」。
**原因**：排程「Teacher AI Worker」用 SYSTEM 帳號執行（不需要知道 Windows 登入密碼）。MEGAcmd 若只裝在某個使用者的 `C:\Users\<名稱>\AppData\Local\MEGAcmd`，SYSTEM 看不到；而 MEGAcmd 啟動背景伺服器時是問 Windows 本機資料夾位置，不看環境變數。
**已做的處理（在 Worker 電腦，一次性）**：
1. `.local-worker.env` 設 `MEGACMD_EXTRA_DIRS=C:\Users\<名稱>\AppData\Local\MEGAcmd`（程式會加進搜尋路徑；實作在 `teacher_app/storage/worker_runtime.py`）。
2. 把該資料夾複製一份到 `C:\Windows\System32\config\systemprofile\AppData\Local\MEGAcmd`（`robocopy 來源 目的地 /E`；`.megaCmd` 快取資料夾被占用的警告可忽略）。**重裝或升級使用者帳號底下的 MEGAcmd 後，要重複這個複製。**
**重啟注意**：只執行 `Stop-ScheduledTask` 不一定會關掉舊的 python / PowerShell 子程序，會造成 AI Worker 同時跑兩份、工作卡在 15%。重啟請先關閉命令列含 `TeacherWorker` 的 python/powershell 程序再啟動排程（見 `docs/WORKER_BOOTSTRAP.md` 或請開發者提供指令）。
