# Teacher 6.7 — Smart Learning Content

6.7 is additive and retains `pgy_app:app`, server-authoritative grading, answer-key/review-source protection, 6.6 signing, backup safety and legacy schemas. Migration `0067-smart-learning-content` adds learning progress, native text index, media jobs and preview-only DOCX/Atlas imports without deleting or overwriting data.

PPTX text is read from OOXML and PDF text from PyMuPDF; scanned PDFs report no searchable text. DOCX imports remain preview-first. Media processing requires a separately deployed durable worker; the web request never transcodes. FFmpeg is capability-detected and may be absent. Render worker deployment is documented only and has not been created.

ReviewSource 2.0 remains post-submit only and accepts legacy `timeSeconds` plus `timeStart`, `timeEnd` and bounded Atlas regions. Backups remain insert-missing-only.

## Render Scheme B — durable material processing

Teacher 6.7 uses one PostgreSQL-backed source of truth, `material_jobs`.  It is
the only queue used to claim, retry, recover stale work, and record completion.
`media_processing_jobs` is linked supporting metadata for media jobs; it is not
a second consumer queue.

The Web Service starts only `gunicorn … pgy_app:app`.  With
`MATERIAL_BACKGROUND_JOBS=true` it may safely accept an upload and create a
job, but it never forks or supervises `material_worker.py`.  The separate
Render Background Worker starts `python -u material_worker.py` with
`MATERIAL_WORKER_ENABLED=true`.  Local development remains supported by running
that command explicitly in a second terminal; a local staging fallback is only
for that single-machine case.

For Render, the Web Service uploads the received file to shared staging before
creating a runnable DB job.  Shared staging uses the existing MEGA primary
storage (with the established Google Drive fallback when MEGA is full) in the
`_staging/material-jobs/<job-id>/` namespace.  A job records only backend,
object key, original name, SHA-256 and byte count—never credentials or a shared
local path.  The Worker downloads the object into its own `TemporaryDirectory`,
rechecks extension/signature, ZIP hardening, size and SHA-256, then calls the
existing trusted conversion/upload flow.  Success deletes the staging object;
retry and terminal failures retain it until the configured retention cleanup.

The additive `0067-render-worker-shared-staging` marker extends existing 0067
installs with staging metadata and media-job linkage.  It is SQLite and
PostgreSQL safe and does not overwrite legacy rows.  `/health` intentionally
does not depend on worker availability.  Admin-only operational endpoints show
aggregate queue counts, staging backend and FFmpeg/LibreOffice capability, but
not credentials, database URLs, object keys or absolute paths.

`render.yaml` defines a free-plan worker blueprint, but this repository change
does not create or deploy it.  Before creating the service, confirm Render's
current Background Worker free-plan availability and any idle/runtime/network
costs in the Render dashboard; do not silently upgrade a plan.  Both services
must be configured with the same PostgreSQL, MEGA and Google Drive credentials,
and the worker must have LibreOffice and FFmpeg available in its Docker image.
