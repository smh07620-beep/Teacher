# AI PowerPoint Phase 4 — teaching-quality automation (0104)

Phase 4 extends the existing reviewed/immutable PowerPoint workflow. It does not
replace the existing RBAC, publication receipts, shared storage, Worker queue, or
provenance model.

## Migration

Apply `0104-ai-presentation-quality-automation` before enabling the Phase 4 UI.
The migration is additive for SQLite and PostgreSQL and preserves all historical
presentation rows and publication receipts.

It adds:

- `ai_presentations.quality_manifest_json`
- `ai_presentations.render_metrics_json`
- `ai_presentations.render_ruleset_version`
- nullable `ai_presentation_jobs.idempotency_key` plus a unique index for
  regenerate/re-render requests

## Quality rules

The canonical ruleset is `phase4-v1`. The Worker applies deterministic layout
selection after the draft has already passed the existing slide/block allow-list.
Unknown model-supplied layout values never become template lookups.

Phase 4 performs bounded continuation splitting for dense text, preserves table
headers across table pages, paginates comparison blocks, and keeps image assets
restricted to checksummed PNG/JPEG objects from the existing shared provider
namespace. Browser URLs, HTML, and iframes remain unsupported.

Image blocks can request `contain` or `crop`. Captions and source labels are
plain bounded text only; storage keys and RAG chunk identifiers are not placed on
the visible slide. Allow-listed provenance remains in PowerPoint metadata and
speaker notes.

## Publish gate

`GET /api/ai-presentations/<id>/quality` returns the persisted or deterministically
recomputed quality manifest and render observability.

Publishing rules:

- `error`: publication is rejected with HTTP 409.
- `warning`: an authorized publisher must explicitly acknowledge the warnings.
  The acknowledgement is append-only audited and copied into the immutable
  publication snapshot.
- `pass`: the normal Phase 3 immutable publication flow continues.

A teacher-uploaded replacement `.pptx` is marked with
`MANUAL_ARTIFACT_UNCHECKED`; it remains usable but requires explicit warning
acknowledgement before publication because the Worker did not reflow that binary.

## Regenerate / re-render

`POST /api/ai-presentations/<id>/regenerate` creates a new immutable draft
revision and queues the existing AI presentation Worker protocol. It never
rewrites an old artifact. A deterministic idempotency key combines the source
revision, slides/template identity, and the Phase 4 ruleset; repeating the same
request reuses the existing job.

## Deployment

- Render Web and the local AI Worker must keep using the same durable
  `AI_PRESENTATION_STORAGE_BACKEND` provider.
- Restart the AI Worker after deploying the code so it picks up `phase4-v1`.
- No new paid service or headless office dependency is required.
- `AI_PRESENTATION_JOB_MAX_ATTEMPTS` continues to control the existing retry
  ceiling (default 3).
