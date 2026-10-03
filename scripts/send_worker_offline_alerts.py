"""One-shot entry point for critical Worker-offline email alerts."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from teacher_app.notifications.reminders import (
    run_operational_incident_alerts,
    run_worker_offline_reminders,  # backward-compatible callable kept intentionally
)


def main() -> int:
    sent = run_operational_incident_alerts()
    print(f"teacher-operational-incident-alerts sent={sent}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
