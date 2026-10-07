#!/usr/bin/env python3
"""Teacher Worker self-diagnosis entry point.

Run from the Worker checkout (inside its .venv)::

    python worker_doctor.py            # full check, includes a real Kokoro synthesis
    python worker_doctor.py --quick    # skip the slow LibreOffice/Kokoro checks

See ``teacher_app/worker/doctor.py`` for what each check verifies.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from teacher_app.worker.doctor import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
