# Teacher 6.7 — Smart Learning Content

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
service, or modify a production database.
