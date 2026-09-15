# Teacher 6.5 — Modular Architecture & Integration Hardening

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
architecture release with no destructive schema change.
