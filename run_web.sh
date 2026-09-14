#!/usr/bin/env bash
set -euo pipefail

# Scheme B: this is the Render *web* entrypoint only.  MATERIAL_BACKGROUND_JOBS
# means that HTTP requests may create durable jobs; it never means that the web
# container may fork a worker.  Render starts a separate worker service with
# MATERIAL_WORKER_ENABLED=true.

# Phase 3 deployment entrypoint. pgy_app imports the existing app.py and then
# registers PGY assignment/signature/audit routes on the same Flask instance.
exec gunicorn --bind 0.0.0.0:${PORT:-5000} --workers ${WEB_CONCURRENCY:-1} --threads ${GUNICORN_THREADS:-4} --timeout ${GUNICORN_TIMEOUT:-180} pgy_app:app
