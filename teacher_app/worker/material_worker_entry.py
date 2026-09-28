"""Canonical package launcher for the local material Worker."""
from __future__ import annotations

import sys

import material_worker as worker
from teacher_app.worker.media_transcode_compat import install


install(worker)


if __name__ == "__main__":
    sys.exit(worker.main())
