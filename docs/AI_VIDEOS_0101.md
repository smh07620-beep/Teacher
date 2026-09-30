# AI presentation video pipeline (0101 + Phase 5 / 0105)

Phase 5 converts one immutable **approved or published PowerPoint revision** into a teacher-reviewed MP4 while preserving the exact source revision, checksum, RBAC/scope, durable storage, and publication lineage.

## Worker-only pipeline

`approved PowerPoint revision -> download/verify exact PPTX -> Phase 4 cover/pagination alignment -> PowerPoint frame export -> per-slide Kokoro WAV -> slide timeline -> WebVTT/SRT -> FFmpeg MP4 -> shared durable provider`

The Flask Web process only validates scope/RBAC, creates a persistent idempotent job, reports status/quality, and returns provider preview responses. It never receives TTS WAVs, temporary slide images, PowerPoint COM output, FFmpeg inputs, or MP4 bytes.

On the canonical Windows AI Worker, Phase 5 prefers installed desktop Microsoft PowerPoint through a temporary PowerShell COM exporter. This exports the **approved PPTX itself** to 1280×720 PNG frames without adding pywin32. If PowerPoint export is unavailable, the Worker uses the existing safe text-frame fallback and records `FRAME_RENDERER_FALLBACK`; publication then requires explicit warning acknowledgement after preview. A source checksum mismatch remains blocking and never falls back.

Phase 4 automatic cover/continuation/table/comparison pagination is recalculated before narration so the video timeline uses the same rendered page count as the PPTX. Continuation pages do not repeat the original speaker notes; they narrate their page-specific text/table/comparison content instead.

## Quality, retry, and idempotency

Migration `0105-ai-video-production-hardening` adds:

- video generation idempotency keyed by presentation revision + presentation SHA256 + voice + Phase 5 ruleset;
- quality manifests with blocking errors vs review warnings;
- render metrics (`durationMs`, attempts, slide/TTS/FFmpeg counts, frame renderer);
- safe failed-job retry with a bounded attempt limit;
- immutable publication snapshots with source presentation checksum, timeline, renderer, quality state, and warning acknowledgement.

Blocking quality errors prevent approval and publication. Warnings may be approved for teacher review, but formal publication requires an authorized publisher to explicitly acknowledge the warnings; that acknowledgement is audited and written into the immutable publication snapshot.

## Approval and authorization

- The exact source presentation revision must be `approved` or `published`, in the same group/area, with complete durable presentation metadata.
- A generated MP4 is an immutable `draft` video revision. `clinical_teacher` and `group_leader` may approve; `education_admin` and `system_admin` may operate/publish but cannot substitute for teacher approval.
- All create/job/preview/caption/quality/retry/approve/publish routes re-check server-side scope.
- Publication remains idempotent by video revision receipt.
- Tokens, passwords, authorization values, and local paths are rejected before narration/provenance is persisted.

## Worker bootstrap / upgrade

Use the existing canonical one-click bootstrap; Phase 5 does not introduce a second Worker architecture:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup_teacher_worker.ps1 -InstallOptionalTools -InstallTasks -ServiceAccount -TaskUser SYSTEM -StartNow
```

The script safely creates/synchronizes `.venv`, installs `requirements-ai-worker.txt`, verifies FFmpeg, validates configured AI/storage prerequisites, can use the signed-release updater, and registers the existing Material + AI Worker scheduled tasks. Secrets remain only in the gitignored `.local-worker.env` and are never printed or placed on Task Scheduler command lines.

For production-quality frame fidelity, install Microsoft PowerPoint on the Windows AI Worker. Without it, video generation remains available through the warning-gated fallback renderer.

## Deployment

1. Deploy Web and AI Worker from the same `main` revision and apply migrations through `0105`.
2. Keep `AI_VIDEO_STORAGE_BACKEND=auto` (or the same shared R2/OCI/Google Drive/MEGA provider used by PowerPoint). Local storage remains development-only.
3. Run `setup_teacher_worker.ps1` after approved releases to synchronize Worker dependencies and scheduled tasks.
4. Verify `/api/ai-videos/status` reports the Phase 5 ruleset and shared storage availability.
5. Generate from an approved PowerPoint revision, inspect `/quality`, preview MP4/VTT/SRT, then have a clinical teacher or group leader approve before publication.
