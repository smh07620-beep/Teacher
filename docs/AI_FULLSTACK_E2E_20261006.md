# AI full-stack E2E handoff (2026-10-06)

The isolated Product Golden Path GP-11 job runs `tests/run_ai_fullstack.py`.
It starts canonical Flask, SQLite repositories, canonical HTTPS AI Worker,
canonical material Worker entrypoint and a Moto R2-compatible S3 service.
Only inference is deterministic; browser fetches, routes, RBAC, persisted jobs,
claims, material extraction, artifact generation and object storage are real.
No production accounts, Opera connector or hospital Worker are used.

## Completed segments

- A: `tests/playwright/ai-question-fullstack-golden-path.spec.js` generates
  questions through a real job, imports them, publishes an exam, uses a separate
  learner browser context to answer and verifies the persisted score from the
  teacher account after reload.
- B: `tests/playwright/ai-powerpoint-fullstack.spec.js` uploads PDF, DOCX, PPTX,
  PNG and text through Browser → S3 → canonical material Worker. It verifies
  each source and their mixture with an existing material through real outline
  and presentation jobs, source provenance, artifact hashes and downloaded
  nonempty PPTX slide/notes contents. CI installs LibreOffice and FFmpeg.
- C: `tests/playwright/ai-script-fullstack.spec.js` uses existing material,
  uploaded PDF/PPTX and pasted text in one real script job. It edits the actual
  UI, saves a draft, modifies the saved draft (PATCH), approves it, reloads and
  checks exact persisted content, provenance and approval attribution. The
  approved script appears in the narration selector. The reloaded script is
  carried through the existing presentation speaker-notes handoff and checked
  inside the actual downloaded PPTX plus the production video narration reader.
  This proves the existing notes-based video input contract, NOT MP4 generation
  or a new direct video `scriptId` API.

Local Windows source-format runs may explicitly restrict `E2E_SOURCE_FORMATS`
when LibreOffice is absent. The workflow never restricts source formats and
must pass the full PDF/DOCX/PPTX/image/text matrix.

## Completed continuation: D–G

- D: `tests/playwright/ai-audio-fullstack.spec.js` drives the real narration UI,
  canonical persisted audio jobs and canonical HTTPS AI Worker transport. It
  validates the generated WAV object and browser playback. CI inference is
  deterministic; production Kokoro remains a separate acceptance check.
- E: `tests/playwright/ai-video-fullstack.spec.js` drives approved PowerPoint →
  real Worker/FFmpeg → MP4/VTT/SRT → browser review → teacher publication. Linux
  CI uses branded Chrome and requires H.264/AAC support, byte-range delivery,
  positive duration and advancing playback time.
- F: `tests/playwright/ai-subtitle-timed-question-fullstack.spec.js` proves
  generated/approved VTT → timed video question → learner cue unlock → saved
  answer → teacher-visible persisted record.
- G: `tests/playwright/ai-total-golden-path.spec.js` crosses one combined path:
  Browser upload → script → audio → PowerPoint → video → subtitles/questions →
  learner completion → teacher record.

The F/G pair is continuously gated by `.github/workflows/ai-fg-golden-path-checks.yml`.
The A–E paths remain covered by the Product Golden Path/GP-11 job. These
full-stack browser contracts supplement rather than replace production
Kokoro/R2/account acceptance.

## Production acceptance remains separate

After updating BOTH hospital material and AI Workers with `git pull` and restart:
verify current heartbeat SHA, actual Kokoro voices/model warmup and playable
preview/formal audio; verify formal R2 CORS/auth/downloads, actual production
AI inference, real accounts/RBAC/course publication, FFmpeg video and captions,
timestamp question gating and teacher-readable learner records. Use the
`E2E-TEST-20261006` prefix and do not permanently delete existing data.
Passing isolated CI does not prove these production configuration checks.
