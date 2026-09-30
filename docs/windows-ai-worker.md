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

- AI question generation and teacher script drafting use a free-first chain. The normal priority is **Groq → Gemini → local Ollama** when each provider is configured.
- Provider switching is deliberately narrow: only quota exhausted / rate limit / timeout / provider unavailable errors may fall through. Prompt validation, malformed JSON, unsupported material, authorization, or other deterministic errors do **not** silently switch providers.
- AI narration uses **local Kokoro** on the hospital Worker PC.
- Audio/video transcription can use **local faster-whisper** when the cloud path is unavailable and the final local LLM fallback is used.
- OpenAI is not inserted into the automatic free fallback chain.
- Narration output is WAV and is stored in the existing Cloudflare R2 bucket.

The local fallback stack is installed only on the Worker host through `requirements-ai-worker.txt`; Render Web stays lightweight and only validates/enqueues AI jobs.

### What happens when free cloud quota is exhausted

```text
AI question / teacher script
        ↓
Groq
        ↓ quota / 429 / temporary unavailable only
Gemini
        ↓ quota / 429 / temporary unavailable only
Ollama on the trusted Worker
        ↓
result keeps the actual provider/model provenance
```

If a provider returns a normal validation/content/JSON error, the job fails with that error instead of hiding it by hopping providers. This prevents a malformed request from being retried across every service.

Local Ollama is optional and **disabled by default**. Before enabling it, install Ollama on the Worker, pull the configured model, and confirm the local service is reachable. The example uses a small Chinese-capable model suitable as a CPU fallback:

```powershell
ollama pull qwen3:4b
ollama run qwen3:4b "請回覆：本機 AI 正常"
```

Then set locally in `.local-worker.env`:

```text
AI_FREE_FALLBACK_ENABLED=true
OLLAMA_ENABLED=true
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:4b
OLLAMA_TIMEOUT_SECONDS=240
```

For local speech-to-text:

```text
LOCAL_WHISPER_ENABLED=true
LOCAL_WHISPER_MODEL=small
LOCAL_WHISPER_DEVICE=cpu
LOCAL_WHISPER_COMPUTE_TYPE=int8
```

`faster-whisper` downloads its selected model on first use. That first local transcription can therefore take longer than later jobs. The local fallback currently handles text, subtitle, audio, and video content that can be reduced to text/transcript. Pure image-only teaching material remains fail-closed until a hospital-approved local vision/OCR model is configured; it is not guessed from unsupported pixels.

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
AI_FREE_FALLBACK_ENABLED=true
GROQ_API_KEY=...
GEMINI_API_KEY=...
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

Edit `.local-worker.env` locally. `run_ai_worker_autostart.ps1` automatically synchronizes `requirements-ai-worker.txt` the first time it starts (and again only when that file changes or required imports are unavailable), so Kokoro, Gemini SDK, and faster-whisper stay out of the Render Web dependency set.

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

For the optional local LLM fallback:

```powershell
ollama list
Invoke-RestMethod http://127.0.0.1:11434/api/tags
```

In Event Viewer, inspect **Windows Logs → Application** and filter the `TeacherAIWorker` source. Event 1100 indicates the AI supervisor started. Warnings 2201/2202 mean narration or free-provider configuration is incomplete without exposing secret values. Errors 3101/3103/3104/3105 indicate missing production DB, missing runtime prerequisites, launch failure, or restart exhaustion.

A working AI Worker prints `started queues=ai_questions,media_scripts,media_audio free_fallback=enabled`. The first Kokoro narration, faster-whisper transcription, or local model initialization can be slower because model files may be entering the normal local cache. Web remains responsible only for enqueue/status APIs; long AI execution stays off the Render Web process.
