# Windows same-host Material + AI Worker

Teacher can run the Material Worker and the dedicated AI Worker on the **same trusted Windows computer**. They share one repository checkout, one Python `.venv`, and one gitignored `.local-worker.env`, but remain separate processes and separate Task Scheduler tasks so a long FFmpeg/LibreOffice job cannot block AI question/script/narration work.

## Process layout

```text
C:\TeacherWorker
├─ Teacher Material Worker
│  └─ run_material_worker_autostart.ps1
└─ Teacher AI Worker
   └─ run_ai_worker_autostart.ps1
```

The Material Worker remains the only local release-update owner. `run_ai_worker_autostart.ps1` deliberately does **not** run Git/update logic, which avoids two startup processes racing to modify the same checkout.

## Required local configuration

Copy `.local-worker.env.example` to `.local-worker.env` and fill the values only on the trusted Worker host. Do not commit the resulting file.

The Material Worker keeps using:

```text
TEACHER_BASE_URL=https://your-teacher.onrender.com
MATERIAL_WORKER_TOKEN=...
```

The AI Worker additionally requires the same production database used by Render Web so it can consume the durable AI queues:

```text
DATABASE_URL=postgresql://...
AI_EXTERNAL_PROCESSING_ENABLED=true
AI_PROVIDER=groq
GROQ_API_KEY=...
```

AI narration additionally requires:

```text
OPENAI_API_KEY=...
OPENAI_TTS_MODEL=gpt-4o-mini-tts
OPENAI_TTS_VOICE=marin
R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET_NAME=...
```

`OPENAI_API_KEY` and the R2 values must also exist in the Render Web environment because Web checks narration availability before accepting a narration job. Never place any real key/password/token in Git, frontend JavaScript, Task Scheduler arguments, or screenshots.

## Install on the existing Worker computer

Use the existing checkout and shared virtual environment. From an elevated Windows PowerShell:

```powershell
cd C:\TeacherWorker
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .local-worker.env.example .local-worker.env
```

Edit `.local-worker.env` locally, then install **both** startup tasks with one command. The simplest deployment for the dedicated Worker PC is SYSTEM, provided SYSTEM can read the checkout/env file and use the configured storage providers:

```powershell
.\install_teacher_workers.ps1 -ServiceAccount -TaskUser SYSTEM -StartNow
```

For a hospital/domain service user, omit `-ServiceAccount`; the combined installer asks for the Windows password once and passes the credential to both Task Scheduler registrations:

```powershell
.\install_teacher_workers.ps1 -TaskUser "HOSPITAL\teacher-worker" -StartNow
```

This creates:

- `Teacher Material Worker` — existing material conversion/publish pipeline.
- `Teacher AI Worker` — `ai_questions`, `media_scripts`, and `media_audio` queues.

Both use **At startup**, `StartWhenAvailable`, and Task Scheduler restart-on-failure. Their own supervisors also perform bounded crash restart. The AI supervisor writes non-secret Windows Application events under source `TeacherAIWorker`; the existing material supervisor continues to use `TeacherMaterialWorker`.

## Verify

```powershell
Get-ScheduledTask -TaskName "Teacher Material Worker","Teacher AI Worker" |
  Select-Object TaskName,State

Get-ScheduledTaskInfo -TaskName "Teacher AI Worker"
Get-Process python,pythonw -ErrorAction SilentlyContinue
```

In Event Viewer, inspect **Windows Logs → Application** and filter the `TeacherAIWorker` source. Event 1100 indicates the AI supervisor started. Warnings 2201/2202 mean narration or provider configuration is incomplete without exposing the secret values. Errors 3101/3103/3104/3105 indicate missing production DB, missing runtime prerequisites, launch failure, or restart exhaustion.

A working AI Worker prints `started queues=ai_questions,media_scripts,media_audio`. Web remains responsible only for enqueue/status APIs; long AI execution stays off the Render Web process.
