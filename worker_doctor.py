#!/usr/bin/env python3
"""Teacher Worker self-diagnosis entry point.

Run from the Worker checkout (inside its .venv)::

    python worker_doctor.py            # full check, includes a real Kokoro synthesis
    python worker_doctor.py --quick    # skip the slow LibreOffice/Kokoro checks

See ``teacher_app/worker/doctor.py`` for what each check verifies.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _preload_env_file() -> None:
    """Load .local-worker.env BEFORE importing any teacher_app module.

    teacher_app.storage.providers captures R2_* / MEGA_* once, at import time, so
    reading the env file later makes the doctor report configured storage as
    "not set". utf-8-sig drops the BOM that Notepad/PowerShell may add.
    """
    path = Path(__file__).resolve().parent / ".local-worker.env"
    argv = sys.argv[1:]
    for index, arg in enumerate(argv):
        if arg == "--env-file" and index + 1 < len(argv):
            path = Path(argv[index + 1])
        elif arg.startswith("--env-file="):
            path = Path(arg.split("=", 1)[1])
    if not path.is_file():
        return
    line = re.compile(r"^\s*([^#=\s]+)\s*=\s*(.*?)\s*$")
    for text in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        match = line.match(text)
        if match:
            os.environ[match.group(1)] = match.group(2)


_preload_env_file()

from teacher_app.worker.doctor import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
