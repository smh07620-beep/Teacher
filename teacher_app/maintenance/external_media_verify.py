"""Periodic external-media availability verification command.

Example:
    python -m teacher_app.maintenance.external_media_verify --older-than-minutes 360 --limit 100
"""
from __future__ import annotations

import argparse
import json

from teacher_app.config import external_media_hospital_cdn_hosts
from teacher_app.materials import external_media


DEFAULT_OLDER_THAN_MINUTES = 360
DEFAULT_LIMIT = 100


def run_periodic_verification(
    *,
    older_than_minutes: int = DEFAULT_OLDER_THAN_MINUTES,
    limit: int = DEFAULT_LIMIT,
    http_request=None,
) -> dict:
    """Verify only due rows; never changes material publication/deletion state."""

    return external_media.verify_due_external_media(
        allow_hosts=external_media_hospital_cdn_hosts(),
        older_than_minutes=older_than_minutes,
        limit=limit,
        http_request=http_request,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Verify external teaching-media availability")
    parser.add_argument(
        "--older-than-minutes",
        type=int,
        default=DEFAULT_OLDER_THAN_MINUTES,
        help="Only re-check rows whose last verification is at least this old (default: 360).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help="Maximum rows per run, bounded to 1..500 (default: 100).",
    )
    args = parser.parse_args(argv)
    result = run_periodic_verification(
        older_than_minutes=max(1, min(7 * 24 * 60, int(args.older_than_minutes))),
        limit=max(1, min(500, int(args.limit))),
    )
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

