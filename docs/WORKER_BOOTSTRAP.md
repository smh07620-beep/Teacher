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
3. Python version/import self-test (`python-pptx`, Kokoro, faster-whisper, Gemini client, PostgreSQL client);
4. FFmpeg availability;
5. optional Ollama installation and configured model availability;
6. required Worker configuration without printing secret values;
7. stable `MATERIAL_WORKER_ID` recommendation;
8. PowerPoint/video shared durable-provider readiness;
9. existing Material + AI Worker Task Scheduler installation;
10. optional Worker task restart and state summary.

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

`-InstallOptionalTools` allows the script to use `winget` for missing FFmpeg and, only when `OLLAMA_ENABLED=true`, missing Ollama. It never downloads an Ollama model that `ollama list` already reports as installed.

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
- PowerPoint rendering: python-pptx;
- video composition: FFmpeg.

Provider fallback behavior remains in application code: validation/malformed-input errors do not trigger provider hopping.

When `OLLAMA_ENABLED=false`, the bootstrap does not install/pull a local LLM merely because Ollama support exists. When it is enabled, an existing configured model is reused; a pull happens only when the model is absent and downloads are allowed.

## Production verification

After setup/restart:

1. both `Teacher Material Worker` and `Teacher AI Worker` scheduled tasks should exist;
2. the AI Worker should emit its normal startup/heartbeat events without exposing configuration values;
3. Web and Worker must use the same production `DATABASE_URL` and shared durable storage configuration;
4. FFmpeg must be discoverable in the scheduled-task environment before AI video jobs are relied on;
5. run one controlled `approved PowerPoint -> AI video -> preview -> teacher approval -> publish` smoke test.

## Phase 2 readiness

Video Phase 1 is sufficient to enter the next authoring stage. Phase 1 already provides the durable job/artifact, worker-only TTS/FFmpeg rendering, preview, teacher approval, publication receipt, scope enforcement, and provenance boundaries.

The next coherent slice is **AI Video Phase 2 authoring**, not another Phase 1 pipeline:

- editable narration per slide;
- bounded voice/speed controls;
- regenerate one slide's narration/audio without changing the approved source PowerPoint;
- edit subtitle text/timing and slide hold duration;
- rebuild the full MP4 through the Worker;
- immutable video revision lineage (`parentRevisionId` / `videoFamilyId`) rather than overwriting a published artifact;
- preview -> clinical-teacher/group-leader approval -> idempotent publication using the existing RBAC/storage model.

Phase 2 should remain additive and reuse `ai_video_*`, the current AI Worker queue, durable provider, heartbeat/stale recovery, and existing approval boundary. It should not introduce a browser-side video renderer or a second media queue architecture.
