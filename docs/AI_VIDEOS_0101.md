# AI presentation video Phase 1 (0101)

Phase 1 converts one immutable **approved or published PowerPoint revision** into a teacher-reviewed MP4. It does not replace the existing presentation, narration, subtitle, RAG, or storage architecture.

## Worker-only pipeline

`approved PowerPoint revision -> per-slide speaker notes/text -> local Kokoro WAV -> slide timeline -> WebVTT/SRT -> FFmpeg MP4 -> shared durable provider`

The Flask Web process only validates scope/RBAC, creates a persistent job, reports status, and returns a provider preview response. It never receives TTS WAVs, temporary slide images, FFmpeg inputs, or MP4 bytes.

The dedicated `ai_question_worker.py` takes one video job per loop alongside the existing queues. It persists heartbeat-style progress and requeues only stale `processing` work after `AI_VIDEO_JOB_STALE_SECONDS`.

## Approval, publication, and provenance

- The exact source presentation revision must be `approved` or `published`, in the same group/area, with a complete durable presentation artifact.
- A generated MP4 is a new immutable `draft` video revision. `clinical_teacher` and `group_leader` may approve; `education_admin` and `system_admin` may operate/publish but cannot substitute for teacher approval.
- Publication creates an idempotent receipt keyed by video revision.
- Video records retain only identifiers, checksums, duration, provider/model/voice labels and timeline data. Tokens, passwords, authorization values, and local paths are rejected before narration/provenance is persisted.
- Provider fallback is not attempted for invalid source revisions, malformed metadata, or unsafe narration text. Existing local/free TTS and subtitle policies remain in force.

## Deployment

1. Apply migration `0101-ai-presentation-videos` after 0099/0100.
2. Deploy Web and the dedicated AI Worker from the same revision.
3. Keep `AI_VIDEO_STORAGE_BACKEND=auto` (or point it to the same configured R2/OCI/Google Drive/MEGA provider as PowerPoint). Local video storage is disabled unless explicit single-host development opt-in is set.
4. Install the existing worker requirements and ensure `ffmpeg` is available on the AI Worker. `python-pptx` brings Pillow for the temporary slide images.
5. Verify `/api/ai-videos/status`; generate only from an approved PowerPoint revision, preview it, then have a clinical teacher or group leader approve before publication.
