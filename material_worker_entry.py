"""Canonical local material Worker launcher with narrow media compatibility."""
from __future__ import annotations

import sys

import material_worker as worker
from teacher_app.worker.media_transcode_compat import install


install(worker)


if __name__ == "__main__":
    sys.exit(worker.main())
