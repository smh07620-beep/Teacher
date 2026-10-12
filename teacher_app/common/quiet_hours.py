"""Overnight quiet window (Taiwan time) so the free Render service can sleep.

Render's free web service sleeps after 15 minutes without inbound requests and
the workspace only gets 750 free instance hours per month; a service that never
sleeps uses 744 of them.  Nobody uploads or generates AI content between 01:00
and 06:00, so during that window the hospital Workers stop polling and the
operational alert job stays silent.  Learners can still read: the first request
simply wakes the site (about one minute).

``TEACHER_QUIET_HOURS`` is ``"HH:MM-HH:MM"`` in Taiwan time (UTC+8, no DST);
``off``/``none``/``0`` disables it.  The Workers pass ``DEFAULT_WORKER_QUIET_HOURS``
as their default so the hospital PC needs no new configuration; every other
caller (Web, GitHub alert job) is off unless the variable is set.
"""
from __future__ import annotations

import datetime as dt
import os

TAIWAN_TZ = dt.timezone(dt.timedelta(hours=8))
ENV_NAME = "TEACHER_QUIET_HOURS"
DEFAULT_WORKER_QUIET_HOURS = "01:00-06:00"
_OFF_VALUES = {"", "off", "none", "false", "0", "no", "disabled"}


def parse_quiet_hours(spec: str | None) -> tuple[int, int] | None:
    """Return ``(start_minute, end_minute)`` of day, or ``None`` when disabled/invalid."""
    text = str(spec or "").strip().lower()
    if text in _OFF_VALUES:
        return None
    try:
        left, right = text.replace(" ", "").split("-", 1)
        start_h, start_m = (int(part) for part in left.split(":", 1))
        end_h, end_m = (int(part) for part in right.split(":", 1))
    except (ValueError, TypeError):
        return None
    if not (0 <= start_h <= 23 and 0 <= end_h <= 24 and 0 <= start_m <= 59 and 0 <= end_m <= 59):
        return None
    start, end = start_h * 60 + start_m, end_h * 60 + end_m
    if start == end:
        return None
    return start, end % (24 * 60)


def _spec(default: str | None) -> str | None:
    raw = os.environ.get(ENV_NAME)
    return raw if raw is not None else default


def _minute_of_day(now: dt.datetime | None) -> int:
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    local = current.astimezone(TAIWAN_TZ)
    return local.hour * 60 + local.minute


def in_quiet_hours(
    now: dt.datetime | None = None,
    *,
    default: str | None = None,
    grace_minutes: int = 0,
) -> bool:
    """True while inside the quiet window, extended by ``grace_minutes`` after it ends."""
    window = parse_quiet_hours(_spec(default))
    if window is None:
        return False
    start, end = window
    day = 24 * 60
    length = (end - start) % day
    elapsed = (_minute_of_day(now) - start) % day
    return elapsed < min(day, length + max(0, int(grace_minutes)))


def seconds_until_quiet_end(
    now: dt.datetime | None = None,
    *,
    default: str | None = None,
) -> int:
    """Seconds until the window ends (0 when outside it)."""
    window = parse_quiet_hours(_spec(default))
    if window is None or not in_quiet_hours(now, default=default):
        return 0
    _start, end = window
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    local = current.astimezone(TAIWAN_TZ)
    minutes_left = (end - (local.hour * 60 + local.minute)) % (24 * 60)
    return max(1, minutes_left * 60 - local.second)


__all__ = [
    "DEFAULT_WORKER_QUIET_HOURS",
    "ENV_NAME",
    "TAIWAN_TZ",
    "in_quiet_hours",
    "parse_quiet_hours",
    "seconds_until_quiet_end",
]
