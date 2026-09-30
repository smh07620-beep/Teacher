# AI presentation video pipeline (0101 + Phase 5/6, schema through 0105)

Phase 6 converts one immutable **approved or published PowerPoint revision** into a teacher-reviewed MP4 while preserving the exact source revision, checksum, RBAC/scope, durable storage, renderer provenance, and publication lineage.

## Worker-only pipeline

`approved PowerPoint revision -> download/verify exact PPTX -> Phase 4 cover/pagination alignment -> PowerPoint COM OR LibreOffice headless OR safe fallback -> per-slide Kokoro WAV -> slide timeline -> WebVTT/SRT -> FFmpeg MP4 -> shared durable provider`

The Flask Web process only validates scope/RBAC, creates a persistent idempotent job, reports status/quality, and returns provider preview responses. It never receives TTS WAVs, temporary slide images, PowerPoint/LibreOffice output, FFmpeg inputs, or MP4 bytes.

## Phase 6 renderer chain

The canonical local AI Worker resolves frames in this order:

1. `powerpoint-com` — on Windows, try the approved PPTX through desktop Microsoft PowerPoint with a bounded timeout. This gives the best fidelity when PowerPoint is installed, activated, and COM automation actually works.
2. `libreoffice-headless` — if PowerPoint is expired, unlicensed, unavailable, fails COM, or exceeds the timeout, use the free LibreOffice renderer. LibreOffice converts the exact approved PPTX to PDF with an isolated temporary profile; Worker-only PyMuPDF then rasterizes every page to 1280×720 frames.
3. `text-fallback` — if both full-deck renderers fail, use the existing safe deterministic text renderer. This keeps the job recoverable but creates a publication warning that requires explicit human acknowledgement.

The Worker records every renderer attempt in `renderMetrics.rendererAttempts`; it never exposes local executable paths. A PowerPoint COM timeout is treated as a renderer failure, **not** a whole-job failure, so an expired Microsoft 365/Office installation cannot block the LibreOffice fallback. If the host is known to have unusable PowerPoint, set `AI_VIDEO_POWERPOINT_COM_ENABLED=false` to skip COM immediately.

A source PPTX download/checksum failure is different: that is blocking. Phase 6 never substitutes JSON/text frames when the immutable source artifact itself cannot be retrieved and verified.

## Quality rules

The Phase 6 ruleset is `video-phase6-v1`.

- `powerpoint-com`: no renderer warning when the rest of the quality checks pass.
- `libreoffice-headless`: `FRAME_RENDERER_COMPATIBILITY` warning. The teacher/publisher must preview font/layout compatibility before formal publication.
- `text-fallback`: `FRAME_RENDERER_FALLBACK` warning. The publisher must explicitly acknowledge the fallback after preview.
- unknown renderer, missing source checksum, invalid/mismatched timeline, or missing captions: blocking error.

Older video rulesets receive `RENDER_RULESET_OUTDATED` when reviewed after the Phase 6 upgrade. They remain readable; publication requires review/acknowledgement or a new video generation under the current ruleset.

## Quality, retry, and idempotency

Migration `0105-ai-video-production-hardening` remains the newest schema migration; Phase 6 needs no new columns because renderer attempts are stored inside the existing render-metrics JSON.

The existing 0105 model provides:

- video generation idempotency keyed by presentation revision + presentation SHA256 + voice + quality ruleset;
- quality manifests with blocking errors vs review warnings;
- render metrics (`durationMs`, attempts, slide/TTS/FFmpeg counts, selected renderer and renderer attempts);
- safe failed-job retry with a bounded attempt limit;
- immutable publication snapshots with source presentation checksum, timeline, renderer attempts, quality state, and warning acknowledgement.

Because the ruleset changed from Phase 5 to Phase 6, requesting a video for the same PPT revision/voice creates a Phase 6 generation key rather than silently reusing a Phase 5 result.

## Approval and authorization

- The exact source presentation revision must be `approved` or `published`, in the same group/area, with complete durable presentation metadata.
- A generated MP4 is a `draft` video revision. `clinical_teacher` and `group_leader` may approve; `education_admin` and `system_admin` may operate/publish but cannot substitute for teacher approval.
- All create/job/preview/caption/quality/retry/approve/publish routes re-check server-side scope.
- Publication remains idempotent by video revision receipt.
- Tokens, passwords, authorization values, and local paths are rejected before narration/provenance is persisted.
- The teacher workspace shows the selected renderer, quality state, renderer attempts, preview MP4, VTT/SRT, teacher approval, and publication warning gate.

## Worker bootstrap / upgrade

Use the existing canonical one-click bootstrap; Phase 6 does not introduce a second Worker architecture:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup_teacher_worker.ps1 -InstallOptionalTools -InstallTasks -ServiceAccount -TaskUser SYSTEM -StartNow
```

`-InstallOptionalTools` may install both FFmpeg and LibreOffice with `winget`. LibreOffice uses package ID `TheDocumentFoundation.LibreOffice`. The bootstrap also synchronizes `requirements-ai-worker.txt` (including Worker-only PyMuPDF), reports safe renderer candidate IDs, validates AI/storage prerequisites, and registers the existing Material + AI Worker scheduled tasks.

Secrets remain only in the gitignored `.local-worker.env` and are never printed or placed on Task Scheduler command lines.

Useful Phase 6 local settings:

```dotenv
AI_VIDEO_POWERPOINT_COM_ENABLED=true
AI_VIDEO_POWERPOINT_COM_TIMEOUT_SECONDS=45
AI_VIDEO_LIBREOFFICE_PATH=
AI_VIDEO_LIBREOFFICE_TIMEOUT_SECONDS=120
```

If Microsoft PowerPoint is expired or intentionally not used on the Worker, set `AI_VIDEO_POWERPOINT_COM_ENABLED=false`; LibreOffice becomes the first full-deck renderer. There is no requirement to renew Microsoft 365 solely for AI video generation.

## Deployment

1. Deploy Web and AI Worker from the same `main` revision and keep migrations applied through `0105`.
2. Keep `AI_VIDEO_STORAGE_BACKEND=auto` (or the same shared R2/OCI/Google Drive/MEGA provider used by PowerPoint). Local storage remains development-only.
3. Run `setup_teacher_worker.ps1 -InstallOptionalTools` on the trusted Windows Worker so FFmpeg, LibreOffice, PyMuPDF, Kokoro, and the existing scheduled tasks are ready.
4. Verify AI Worker startup reports `powerpoint-com`, `libreoffice-headless`, and `text-fallback` candidate states without exposing local paths.
5. Verify `/api/ai-videos/status` reports `video-phase6-v1` plus the Worker-resolved renderer policy.
6. Generate from an approved PowerPoint revision, inspect renderer attempts and `/quality`, preview MP4/VTT/SRT, then have a clinical teacher or group leader approve before publication.
