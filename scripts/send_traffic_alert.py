"""One-shot traffic alert, run from GitHub Actions.

Render's free web services cannot send mail (outbound SMTP ports are blocked), so
the in-app alert in ``traffic_meter`` never reaches anyone from there.  GitHub
Actions can: it reads the same ``traffic_usage`` table and sends the same mail,
sharing the ``traffic_alerts`` table so each threshold is mailed once per month.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from teacher_app.maintenance.traffic_meter import TrafficMeter


def main() -> int:
    if not os.environ.get("TRAFFIC_ALERT_EMAIL", "").strip():
        print("::error::TRAFFIC_ALERT_EMAIL is empty (set the GitHub secret TRAFFIC_ALERT_EMAIL).", flush=True)
        return 1
    meter = TrafficMeter()
    summary = meter.month_summary()
    sent = meter.check_alerts()
    print(
        f"teacher-traffic-alert month={summary['month']} totalGb={summary['totalGb']} "
        f"thresholds={summary['thresholdsGb']} newlySent={sent}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
