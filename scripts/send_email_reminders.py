"""One-shot entry point for scheduled learning/exam email reminders."""
from __future__ import annotations
import sys
from teacher_app.notifications.reminders import run_due_reminders

def main() -> int:
    sent=run_due_reminders()
    print(f"teacher-email-reminders sent={sent}", flush=True)
    return 0

if __name__=="__main__":
    sys.exit(main())
