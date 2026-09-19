# Teacher architecture history\n\nThis appendix preserves the historical architecture contracts for Teacher 6.5, 6.6, and 6.7. The current ownership contract is ARCHITECTURE.md at the repository root.\n\n# Teacher 6.5 — Modular Architecture & Integration Hardening

Teacher 6.5 is an incremental architecture release built on the existing
Flask application.  It does not replace the legacy application, does not
introduce a second production system, and does not require destructive
database migration.

## Production entrypoint

Production continues to run:

`pgy_app:app`

`pgy_app.py` imports the legacy `app.py` Flask application and incrementally
registers migrations, health checks, PGY workflow adapters, secure exam
attempts, production hardening, upload validation, AI privacy,
backup/restore, and frontend assets.

The application-factory work under `teacher_app:create_app()` remains the
foundation for future migration.  Teacher 6.5 deliberately does not switch
Render to that entrypoint because backward compatibility with the existing
application is the priority for this release.

## Package layout

### `teacher_app/common`

Shared infrastructure:

- database compatibility helpers for SQLite and PostgreSQL
- canonical role normalization
- centralized RBAC permissions
- API error definitions
- compatibility utilities

### `teacher_app/auth`

Authentication is separated into repository, service, and route layers.

Legacy login/logout/user endpoints remain compatible through adapters.

Session invalidation, inactive-account behavior, legacy role aliases, and
production rate limiting remain preserved.

### `teacher_app/exams`

Exam attempts use a server-authoritative model:

- learner starts an immutable server-side attempt
- answer keys remain only in the server-side question snapshot
- learner APIs receive sanitized question projections
- learner-submitted score/correct-count fields are ignored
- grading is performed by the server
- duplicate submit is rejected atomically
- essay questions remain pending human review
- exam record creation and attempt state update share one transaction

### `teacher_app/pgy`

PGY workflow logic is split into:

- `workflow.py` — state machine and transition definitions
- `repository.py` — persistence and conditional updates
- `service.py` — authorization and transactional orchestration
- `routes.py` — HTTP adapter layer

Workflow:

`assigned`
→ `submitted`
→ `teacher_signed`
→ `group_countersigned`
→ `finalized`

Clinical teacher signature is restricted to `clinical_teacher`.

`system_admin` and `education_admin` do not have
`evaluation.sign` permission and may not impersonate a clinical teacher.

PGY transition updates use the current status as part of the conditional
update.  Status mutation and audit insertion are performed in the same
transaction.

## Canonical roles

Teacher 6.5 canonical roles are:

- `student`
- `clinical_teacher`
- `group_leader`
- `education_admin`
- `system_admin`
- `auditor`

Legacy role aliases remain accepted:

- `learner` → `student`
- `teacher` → `clinical_teacher`
- `manager` → `education_admin`

RBAC remains a server-side security boundary.  Frontend role controls are
only usability controls.

## Frontend API handling

`static/shared-core.js` provides the common `AppCore.api` client.

Teacher 6.5 normalizes:

- 401 authentication/session errors
- 403 authorization errors
- 409 concurrent state conflicts
- 413 oversized uploads
- 429 rate limits
- 5xx server errors
- network failures

Both the legacy `error` string and modular `errorDetail` object are supported.

Mutation requests are not automatically retried.

The exam frontend does not require or reconstruct answer keys.

## Backup and restore

Teacher 6.4 data-protection behavior continues in 6.5.

Logical backups contain a manifest, application version, table data, and
SHA256 integrity value.

Restore validates the SHA256 value and remains conservative:
missing records may be inserted, but existing live records are not
overwritten or truncated.

Provider-level database snapshots / PITR remain recommended.

## Upload hardening

Upload validation from 6.4 remains enabled:

- extension/magic-byte validation
- PDF and common image/media validation
- Office OOXML structural validation
- ZIP path-traversal protection
- expanded-size limits
- file-count limits
- suspicious compression-ratio protection

## AI privacy

6.4 AI privacy controls remain enabled.

External AI processing is controlled by environment configuration.
Common patient identifiers are de-identified for supported textual paths.

Direct external processing of media remains disabled by default through:

`AI_EXTERNAL_MEDIA_ALLOWED=false`

No real API key or secret should be written into repository files.

## Schema migrations

Teacher 6.4 introduced:

`0064-baseline`

Teacher 6.5 adds:

`0065-architecture`

`0065-architecture` is intentionally an additive release marker.
No destructive DDL is required for the M1–M7 architecture work.

Migration registration is idempotent.

## Health endpoint

Render continues to probe:

`/health`

Teacher 6.5 health checks:

- application version
- database connectivity
- required migration state

A healthy instance returns HTTP 200.

Database failure or missing required migrations returns HTTP 503 with a
degraded status.

The health endpoint does not expose database URLs, passwords, API keys,
exception details, or stack traces.

## Deployment

Required production entrypoint:

`pgy_app:app`

Typical Render configuration continues to require production environment
settings such as:

- `DATABASE_URL`
- `SECRET_KEY`
- `SESSION_COOKIE_SECURE`
- `CSRF_ORIGIN_CHECK`
- upload safety limits
- backup size limits
- AI privacy controls
- provider API credentials such as `GROQ_API_KEY` when that provider is used

Secrets must be configured through Render/environment settings and must not
be committed to Git.

## Release validation

Teacher 6.5 release CI verifies:

- Python syntax
- full `teacher_app` compilation
- complete unittest discovery
- M5 HTTP integration tests
- M6 frontend API contract tests
- 0065 migration behavior
- health endpoint behavior
- JavaScript syntax
- RBAC invariants
- production entrypoint
- Render security policy
- `VERSION = 6.5.0`

## Rollback

Teacher 6.5 does not require destructive rollback because
`0065-architecture` does not modify live application data.

If application rollback is required:

1. deploy the previous known-good application commit/artifact;
2. keep the existing database intact;
3. do not delete the `schema_migrations` table;
4. do not wipe PGY, exam, account, backup, or audit data.

The 0065 marker can safely remain present because it represents an
architecture release with no destructive schema change.\n\n# Teacher 6.6.0 Architecture and Release

Teacher 6.6.0 is an additive release. It keeps the production entrypoint at
`pgy_app:app`, retains the 6.5 database and API contracts, and applies only
non-destructive database changes through `0066-additive-rbac-pgy-signing`.

## Identity, roles, and PGY signing

- `user_accounts.role` remains the primary legacy role. Existing values such as
  `teacher` normalize to `clinical_teacher` without changing the stored legacy
  value.
- `user_accounts.roles_json` persists normalized multi-role membership. The
  0066 migration fills only empty role sets; it never replaces an existing
  multi-role record.
- New PGY assignments use one signer by default. A configured dual assignment
  requires a different account for the second signature.
- Existing assignments get `sign_mode=legacy` and continue through the original
  student submit, clinical teacher sign, group leader countersign, and education
  admin finalization flow.
- Each signature transition and its audit entry run in the same transaction.
  Failed audit writes roll back the transition.

## Learning and administration experience

- Homepage routing uses the current exam identifier and opens pending exams at
  the correct destination.
- Course and material lists use the 6.6 cache/performance paths. Sequential
  material completion unlocks the next material, while a zero-question exam has
  a clear not-ready state.
- Submitted exam reviews can safely reference PPT/PDF pages, audio/video time,
  image/Atlas regions, and section hints. The learner receives no answer key,
  explanation, or review source before submission.
- Backup and restore controls are limited to system settings. Both system
  settings and people management have a single reachable scroll container.

## Migration, health, and backups

- `0066-additive-rbac-pgy-signing` adds `roles_json`, `sign_mode`,
  `first_signature`, and `second_signature` without removing legacy columns.
- It is idempotent for SQLite and PostgreSQL. Runtime compatibility guards stay
  in place for mixed-version recovery environments.
- `/health` reports database state and requires migrations 0064, 0065, and
  0066; a healthy 6.6.0 response has `migrations.missing = []`.
- Backup manifests remain `teacher-backup-v1`. Restore is insert-missing-only,
  filters rows to the destination schema, and maps legacy backups to additive
  columns without overwriting existing rows.

## Security invariants

- The server is authoritative for grading. Before submit, learner responses do
  not include answer keys, explanations, or review sources.
- `education_admin` and `system_admin` alone cannot sign as a clinical teacher.
  An account may sign clinically only when it actually has the
  `clinical_teacher` role.
- Dual signing always uses two different accounts.
- Production secret/session hardening, AI de-identification and privacy rules,
  upload validation, and backup protections remain enabled.

## Release verification

The release workflow compiles Python, runs the complete unittest suite, checks
the browser JavaScript files, validates version/entrypoint/migration/health
contracts, then publishes the `Teacher-6.6.0-release` ZIP artifact. The ZIP
excludes Git metadata, bytecode, local databases, environment files, local
apply/fix scripts, and failure logs.\n\n# Teacher 6.7 — Smart Learning Content

6.7 is additive and retains `pgy_app:app`, server-authoritative grading, answer-key/review-source protection, 6.6 signing, backup safety and legacy schemas. Migration `0067-smart-learning-content` adds learning progress, native text index, media jobs and preview-only DOCX/Atlas imports without deleting or overwriting data.

PPTX text is read from OOXML and PDF text from PyMuPDF; scanned PDFs report no searchable text. DOCX imports remain preview-first. Media processing requires a separately deployed durable worker; the web request never transcodes. FFmpeg is capability-detected and may be absent. Render worker deployment is documented only and has not been created.

ReviewSource 2.0 remains post-submit only and accepts legacy `timeSeconds` plus `timeStart`, `timeEnd` and bounded Atlas regions. Backups remain insert-missing-only.

## Render Scheme B-Free — durable material processing

Teacher 6.7 uses one PostgreSQL-backed source of truth, `material_jobs`.  It is
the only queue used to claim, retry, recover stale work, and record completion.
`media_processing_jobs` is linked supporting metadata for media jobs; it is not
a second consumer queue.

Render Free runs only the Web Service (`gunicorn … pgy_app:app`) with
`MATERIAL_BACKGROUND_JOBS=true` and `MATERIAL_WORKER_ENABLED=false`. It never
forks or supervises `material_worker.py`; `render.yaml` has no Render Worker
service and therefore does not require a paid Worker plan.

The local/hospital Windows or Linux Worker runs `python -u material_worker.py`
from a trusted machine and makes outbound HTTPS calls only. It uses the distinct
`MATERIAL_WORKER_TOKEN` bearer credential, compared in constant time and never
returned to a browser. The Worker has no production `DATABASE_URL`, learner
session, or `ADMIN_KEY` access. It can only claim, heartbeat, complete, retry,
or fail one atomically-owned `material_jobs` record. Its local MEGA/GDrive
credentials are optional publishing credentials stored only in a local ignored
environment file. This avoids routing large files back through Render.

Small uploads retain the existing compatible Web upload route. Large files use
Browser → R2 direct multipart upload: the Web validates declared name, type,
size and SHA-256, generates an opaque `_staging/material-jobs/<job-id>/` key and
short-lived presigned part URLs, then validates the completed object metadata
and size before creating a runnable job. R2 credentials are never sent to the
browser. R2 is shared staging only; final content remains MEGA primary with the
existing Google Drive fallback.

For the compatible small-upload fallback, the claimed Worker can download only
its own source through a token-protected Web endpoint. This intentionally
proxies only the legacy small-file path; it never exposes a staging key and is
not used for direct R2 media uploads.

The Worker receives a short-lived R2 GET URL after an atomic claim, downloads
to `TemporaryDirectory`, then repeats byte count, SHA-256, extension/magic-byte
and ZIP hardening checks. FFmpeg/FFprobe and LibreOffice are checked at startup
on Windows/Linux using `FFMPEG_PATH`, `FFPROBE_PATH`, and `SOFFICE_PATH` when
provided. Success writes final-material metadata through the protected Web API,
then deletes R2 staging; a cleanup failure marks cleanup pending without
turning a completed material into failed. Retry/terminal failures retain staging
until the configured retention cleanup.

The additive `0067-render-worker-shared-staging` and
`0067-b-free-local-worker` markers extend existing 0067 installs with staging,
worker heartbeat, cleanup, and direct-upload session metadata. They are SQLite
and PostgreSQL safe and do not overwrite legacy rows. `/health` intentionally
does not depend on Worker availability. Admin-only operational endpoints show
aggregate queue counts, heartbeat state, staging backend and capabilities, but
not credentials, database URLs, object keys or absolute paths.

See `LOCAL_WORKER_6_7.md` for Windows setup, Task Scheduler, safe R2 bucket
CORS (specific Teacher origin, never `*`), troubleshooting, and local secret
handling. This repository change does not deploy Render, create a worker
service, or modify a production database.\n\n