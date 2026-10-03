# Error observability closeout

This file records the closeout policy for the 2026-10-03 observability convergence.

Canonical production fallbacks around external I/O, background workers, storage, notification/command-center projections, password-reset email, upload progress, and privacy lookups must emit bounded operational logs. New warnings prefer stable identifiers plus `error_type`; do not add credentials, tokens, email addresses, presigned URLs, file contents, or raw provider exception messages.

External-AI privacy metadata lookup is fail-closed. When external media is disabled and material metadata cannot be verified, the request returns HTTP 503 instead of assuming the material is safe.

Broad catches remain intentional when they are only JSON/legacy-row parsing, transaction rollback followed by re-raise, optional dependency detection, per-item fail-closed authorization filters that would create log floods, or cleanup paths already represented by a persisted failure/cleanup-pending state. `teacher_app.legacy_host` remains compatibility-only and is not a destination for new observability ownership.

Future changes should log at the canonical boundary that first turns a real dependency failure into a fallback. Do not blanket-log every `except Exception`.
