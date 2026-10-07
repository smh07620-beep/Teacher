# Teacher Windows Worker one-click bootstrap / upgrade

`setup_teacher_worker.ps1` is the canonical host bootstrap wrapper for the existing Material Worker + AI Worker scripts. It does **not** create a second updater, scheduler, or supervisor architecture.

It keeps these existing boundaries:

- `update_material_worker.ps1` remains the **only** repository updater and accepts only an explicitly approved annotated release tag (signed by default).
- `install_teacher_workers.ps1` remains the combined Task Scheduler installer.
- `run_material_worker_autostart.ps1` and `run_ai_worker_autostart.ps1` remain the supervisors.
- `.local-worker.env` remains gitignored and is never printed, uploaded, reset, or committed.
- The bootstrap never runs `git reset`, `git clean`, `git stash`, or overwrites a dirty checkout.

## What the bootstrap checks

One command can safely coordinate:

1. optional approved release-tag update through the existing updater;
2. `.venv` creation and `requirements-ai-worker.txt` synchronization;
3. Python version/import self-test (`python-pptx`, PyMuPDF, Kokoro, faster-whisper, Gemini client, PostgreSQL client);
4. FFmpeg availability;
5. LibreOffice availability for the Phase 6 free PowerPoint renderer fallback;
6. safe video renderer candidate summary (`PowerPoint COM -> LibreOffice -> text fallback`) without printing executable paths;
7. optional Ollama installation and configured model availability;
8. required Worker configuration without printing secret values;
9. stable `MATERIAL_WORKER_ID` recommendation;
10. PowerPoint/video shared durable-provider readiness;
11. existing Material + AI Worker Task Scheduler installation;
12. optional Worker task restart and state summary.
13. a connectivity self-test (`worker_doctor.py --quick`, skip with `-SkipDoctor`).

The script does **not** install NVIDIA/CUDA/display drivers. GPU driver management remains a host-admin action.

## First-time setup on the hospital Worker PC

Open **Windows PowerShell as Administrator**, enter the repository, then run:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_teacher_worker.ps1 `
  -InstallOptionalTools `
  -InstallTasks `
  -ServiceAccount `
  -StartNow
```

`-InstallOptionalTools` allows the script to use `winget` for missing FFmpeg and LibreOffice and, only when `OLLAMA_ENABLED=true`, missing Ollama. LibreOffice uses package ID `TheDocumentFoundation.LibreOffice`. It never downloads an Ollama model that `ollama list` already reports as installed.

If `.local-worker.env` does not exist, the script copies `.local-worker.env.example` and exits with warnings until required placeholders are filled locally. Re-run the same command after filling the file.

For a password-backed scheduled-task account, omit `-ServiceAccount`. The existing installer prompts for the Windows password; the password is not taken from environment variables. `-NonInteractive -InstallTasks` therefore requires `-ServiceAccount`.

## Safe upgrade

Code upgrades keep the existing approved-release security boundary. Create/approve the annotated release tag through the normal release process, then run:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_teacher_worker.ps1 `
  -ReleaseRef vX.Y.Z `
  -ReleaseCommit APPROVED_COMMIT_PREFIX `
  -InstallOptionalTools `
  -RestartTasks
```

The wrapper passes the release reference to `update_material_worker.ps1`; it does not pull `main` directly. A dirty working tree is refused before any checkout change.

To upgrade only Python/local tool prerequisites on the already approved checkout, omit `-ReleaseRef` and use `-SkipReleaseUpdate`.

## Dry-run / limited-network modes

```powershell
# Inspect what would be changed.
.\setup_teacher_worker.ps1 -DryRun -SkipReleaseUpdate

# Do not install optional tools or pull a missing Ollama model.
.\setup_teacher_worker.ps1 -SkipDownloads -SkipReleaseUpdate

# Keep the current Python environment untouched.
.\setup_teacher_worker.ps1 -SkipPythonSync -SkipReleaseUpdate
```

Exit codes:

- `0`: bootstrap checks completed without warnings;
- `2`: bootstrap completed but one or more readiness warnings require attention;
- `1`: a safety/prerequisite failure stopped the bootstrap.

## Local AI behavior

The bootstrap follows `.local-worker.env`:

- text generation fallback: Groq -> Gemini -> Ollama when configured;
- local speech-to-text: faster-whisper;
- local narration: Kokoro;
- PowerPoint creation: python-pptx;
- approved PPTX video frame renderer: PowerPoint COM -> LibreOffice headless -> warning-gated safe text fallback;
- LibreOffice PDF rasterization: Worker-only PyMuPDF;
- video composition: FFmpeg.

Provider fallback behavior remains in application code: validation/malformed-input errors do not trigger provider hopping.

When `OLLAMA_ENABLED=false`, the bootstrap does not install/pull a local LLM merely because Ollama support exists. When it is enabled, an existing configured model is reused; a pull happens only when the model is absent and downloads are allowed.

## PowerPoint expired / unlicensed behavior

A working Microsoft PowerPoint installation is optional for AI video production.

Phase 6 uses a bounded COM attempt. If PowerPoint is expired, unlicensed, unavailable, fails COM automation, or hangs until the configured timeout, the video job continues to `libreoffice-headless`. If the Worker is known to have unusable PowerPoint, set:

```dotenv
AI_VIDEO_POWERPOINT_COM_ENABLED=false
```

This skips COM immediately and makes LibreOffice the first full-deck renderer. `AI_VIDEO_POWERPOINT_COM_TIMEOUT_SECONDS` defaults to 45 seconds. `AI_VIDEO_LIBREOFFICE_TIMEOUT_SECONDS` defaults to 120 seconds. `AI_VIDEO_LIBREOFFICE_PATH` may point to `soffice.exe` when LibreOffice is installed in a non-standard location.

LibreOffice render output receives a compatibility warning because fonts/placement can differ slightly from Microsoft PowerPoint; formal publication therefore requires preview/acknowledgement. The safe text fallback has an even stronger warning. Source PPTX download/checksum failures remain blocking and never downgrade to fallback frames.

## Production verification

After setup/restart:

1. both `Teacher Material Worker` and `Teacher AI Worker` scheduled tasks should exist;
2. the AI Worker should emit its normal startup/heartbeat events without exposing configuration values;
3. AI Worker startup should report candidate states for `powerpoint-com`, `libreoffice-headless`, and `text-fallback` without local paths;
4. the hospital AI Worker should use the Render HTTPS 443 control plane (`TEACHER_BASE_URL` + Worker token); direct production `DATABASE_URL` is legacy fallback only, while shared durable storage configuration remains available locally for large artifacts;
5. FFmpeg must be discoverable in the scheduled-task environment before AI video jobs are relied on;
6. LibreOffice should be detected on the Worker when PowerPoint cannot be relied on;
7. run one controlled `approved PowerPoint -> renderer chain -> AI video -> preview -> teacher approval -> publish` smoke test.

## Phase 6 teacher workflow

The existing teacher media workspace now exposes the Phase 6 renderer policy and the actual renderer used for each generated video. Teachers can:

- select an approved PowerPoint revision and Kokoro voice;
- generate an MP4 through the Worker;
- inspect renderer attempts and quality warnings;
- preview MP4 and VTT/SRT;
- have a clinical teacher or group leader approve the draft;
- publish only after any renderer warning is explicitly acknowledged.

This remains additive and reuses `ai_video_*`, the current AI Worker queue, durable provider, heartbeat/stale recovery, and existing approval boundary. It does not introduce browser-side video rendering or a second media queue architecture.

## Compatibility lineage: AI Video Phase 2 authoring

Phase 6 intentionally preserves the earlier AI Video Phase 2 authoring contract instead of replacing it. The authoring lineage still supports **editable narration per slide**, keeps immutable revision links through `parentRevisionId` and `videoFamilyId`, retains the **clinical-teacher/group-leader approval** boundary, and continues to **reuse `ai_video_*`** persistence/queue/runtime ownership. Phase 6 only strengthens renderer resilience, observability, teacher preview, and publication quality gates on top of that existing pipeline.

## Worker doctor (`worker_doctor.py`)

When "every feature exists but they do not connect", run this on the Worker PC
(inside the Worker `.venv`):

```powershell
.venv\Scripts\python.exe worker_doctor.py          # full check
.venv\Scripts\python.exe worker_doctor.py --quick  # skip slow LibreOffice/Kokoro checks
.venv\Scripts\python.exe worker_doctor.py --json   # machine readable
```

It loads `.local-worker.env` exactly like the Task Scheduler supervisors and
verifies, in order: required settings, Web reachability (`/health`), that the
Material and AI Worker tokens are accepted (no job is claimed and no heartbeat
row is created), that the Worker code matches the deployed Web version, FFmpeg /
FFprobe / LibreOffice, final storage preflight, a real R2 write/read/delete,
a real LibreOffice warm-up conversion, and a real Kokoro synthesis. No secret
value is printed. Exit code is `1` when any check fails.

The Material Worker and AI Worker also compare their code with the Web service
at startup and every `WORKER_SITE_VERSION_CHECK_MINUTES` (default 30); the
result is logged and shown in the Worker status panel.
