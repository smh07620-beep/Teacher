"""Single, explicit contract for the currently supported Teacher release."""
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RELEASE_VERSION = "6.8.1"
ENTRYPOINT = "pgy_app:app"
REQUIRED_RELEASE_MIGRATION = "0068-external-interactive-media"

def version_file_value() -> str:
    return ROOT.joinpath("VERSION").read_text(encoding="utf-8").strip()
