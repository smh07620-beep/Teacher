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

## Free-only AI policy

Production keeps `FREE_ONLY_MODE=true`.

- AI question generation / teacher script drafting uses the configured free provider (`AI_PROVIDER=groq` by default).
- AI narration uses **local Kokoro** on the hospital Worker PC.
- OpenAI TTS is not required, not declared in `render.yaml`, and is not called by `media_audio_runtime.py`.
- Narration output is WAV and is stored in the existing Cloudflare R2 bucket.

Kokoro is installed only on the local Worker host through `requirements-ai-worker.txt`; Render Web stays lightweight and only validates/enqueues narration jobs.

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
FREE_ONLY_MODE=true
AI_EXTERNAL_PROCESSING_ENABLED=true
AI_PROVIDER=groq
GROQ_API_KEY=...
```

Free local narration uses:

```text
AI_TTS_PROVIDER=kokoro
KOKORO_MODEL=Kokoro-82M-v1.1-zh
KOKORO_REPO_ID=hexgrad/Kokoro-82M-v1.1-zh
KOKORO_VOICE=zf_xiaoxiao
KOKORO_TTS_SPEED=1.0
```

and the existing R2 configuration:

```text
R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET_NAME=...
```

Never place any real key/password/token in Git, frontend JavaScript, Task Scheduler arguments, screenshots, or chat messages.

## Install on the existing Worker computer

Use the existing checkout and shared virtual environment. From an elevated Windows PowerShell:

```powershell
cd C:\TeacherWorker
git checkout main
git fetch origin
git pull --ff-only origin main

py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .local-worker.env.example .local-worker.env
```

Edit `.local-worker.env` locally. `run_ai_worker_autostart.ps1` automatically synchronizes `requirements-ai-worker.txt` the first time it starts (and again only when that file changes or required imports are unavailable), so Kokoro stays out of the Render Web dependency set.

Then install **both** startup tasks with one command. The simplest deployment for a dedicated Worker PC is SYSTEM, provided SYSTEM can read the checkout/env file and use the configured storage providers:

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

In Event Viewer, inspect **Windows Logs → Application** and filter the `TeacherAIWorker` source. Event 1100 indicates the AI supervisor started. Warnings 2201/2202 mean narration or free-provider configuration is incomplete without exposing secret values. Errors 3101/3103/3104/3105 indicate missing production DB, missing runtime prerequisites, launch failure, or restart exhaustion.

A working AI Worker prints `started queues=ai_questions,media_scripts,media_audio`. The first Kokoro narration may also download the open model/voice files to the normal local model cache. Web remains responsible only for enqueue/status APIs; long AI execution stays off the Render Web process.
