"""One-shot entry point for scheduled learning/exam email reminders."""
from __future__ import annotations

import sys
from pathlib import Path

# When this file is executed directly (``python scripts/send_email_reminders.py``),
# Python puts ``scripts/`` rather than the repository root on sys.path.  Add the
# root explicitly so the canonical ``teacher_app`` package is importable in
# GitHub Actions and local one-shot runs alike.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from teacher_app.notifications.reminders import run_due_reminders


def main() -> int:
    sent = run_due_reminders()
    print(f"teacher-email-reminders sent={sent}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
