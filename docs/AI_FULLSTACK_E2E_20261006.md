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

## Deliberately not started in this round

Per the user's final instruction, finish C and do not leave D half-built.
D (real preview/formal audio job → inspected WAV), E (real FFmpeg → inspected
MP4/captions/storage), F (subtitle/timestamp question learner playback → saved
answers), and G (one combined teacher-to-student path) still need their own
full-stack browser tests. Existing media/F5 integration tests are retained but
are not substitutes for these tests.

## Production acceptance remains separate

After updating BOTH hospital material and AI Workers with `git pull` and restart:
verify current heartbeat SHA, actual Kokoro voices/model warmup and playable
preview/formal audio; verify formal R2 CORS/auth/downloads, actual production
AI inference, real accounts/RBAC/course publication, FFmpeg video and captions,
timestamp question gating and teacher-readable learner records. Use the
`E2E-TEST-20261006` prefix and do not permanently delete existing data.
Passing isolated CI does not prove these production configuration checks.
