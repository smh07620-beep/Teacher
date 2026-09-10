#!/usr/bin/env bash
set -euo pipefail

worker_pid=""
stop_all(){
  if [ -n "${worker_pid}" ] && kill -0 "${worker_pid}" 2>/dev/null; then kill "${worker_pid}" 2>/dev/null || true; fi
}
trap stop_all EXIT INT TERM

case "${MATERIAL_BACKGROUND_JOBS:-true}" in
  0|false|FALSE|no|NO|off|OFF) ;;
  *)
    (
      while true; do
        python -u material_worker.py || true
        echo "[material-worker-supervisor] worker exited; restarting in 3s" >&2
        sleep 3
      done
    ) &
    worker_pid=$!
    ;;
esac

# Phase 3 deployment entrypoint. pgy_app imports the existing app.py and then
# registers PGY assignment/signature/audit routes on the same Flask instance.
exec gunicorn --bind 0.0.0.0:${PORT:-5000} --workers ${WEB_CONCURRENCY:-1} --threads ${GUNICORN_THREADS:-4} --timeout ${GUNICORN_TIMEOUT:-180} pgy_app:app
