#!/usr/bin/env bash
set -euo pipefail

# Scheme B: this is the Render *web* entrypoint only.  MATERIAL_BACKGROUND_JOBS
# means that HTTP requests may create durable jobs; it never means that the web
# container may fork a worker.  A trusted local/hospital worker polls the HTTPS
# worker API with MATERIAL_WORKER_TOKEN.

# Production entrypoint. pgy_app builds the canonical Flask application through
# teacher_app.create_app().
exec gunicorn --bind 0.0.0.0:${PORT:-5000} --workers ${WEB_CONCURRENCY:-1} --threads ${GUNICORN_THREADS:-4} --timeout ${GUNICORN_TIMEOUT:-180} pgy_app:app
