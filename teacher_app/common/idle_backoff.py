"""Adaptive idle polling for the hospital Workers.

Both Workers used to ask the Web app for work every 2 seconds, around the
clock.  On a free Render plan that machine-to-machine chatter was the largest
steady source of outbound bandwidth (about 3 MB/hour), and it also kept the
Supabase pooler busy.  Real work arrives rarely, so after a short run of empty
polls the Worker now waits longer between polls and snaps back to the base
interval the moment it finds work.
"""
from __future__ import annotations

import os

# 2026-10-13: raised from 15 to 45 seconds.  With two Workers idle-polling every
# 15 seconds the steady traffic was about 3.5 MB/hour (roughly 2 GB/month, 40% of
# the free 5 GB Render allowance) before any learner used the site.  A job that
# is queued while the Worker is idle now starts after at most ~45 seconds.
DEFAULT_IDLE_MAX_SECONDS = 45
# Admin screens treat a Worker as online for 120 seconds after its last
# heartbeat, so idle polling must stay well below that.
IDLE_MAX_CEILING_SECONDS = 45
STEPS_PER_DOUBLING = 5


def idle_max_seconds(env_name: str, base_seconds: float) -> float:
    """Longest idle wait, from ``env_name`` (default 45 s, never below base)."""
    raw = os.environ.get(env_name)
    try:
        value = float(raw) if raw is not None and str(raw).strip() != "" else float(DEFAULT_IDLE_MAX_SECONDS)
    except (TypeError, ValueError):
        value = float(DEFAULT_IDLE_MAX_SECONDS)
    return max(float(base_seconds), min(float(IDLE_MAX_CEILING_SECONDS), value))


class IdleBackoff:
    """Exponential-ish idle delay: base, then doubled every few empty polls."""

    def __init__(self, base_seconds: float, max_seconds: float, *, steps_per_doubling: int = STEPS_PER_DOUBLING):
        self.base = max(0.5, float(base_seconds))
        self.maximum = max(self.base, float(max_seconds))
        self.steps = max(1, int(steps_per_doubling))
        self.streak = 0

    def idle_delay(self) -> float:
        """Record one empty poll and return how long to wait before the next."""
        delay = min(self.maximum, self.base * (2 ** (self.streak // self.steps)))
        self.streak += 1
        return delay

    def reset(self) -> None:
        """Work was found: return to the fast base interval."""
        self.streak = 0


__all__ = ["DEFAULT_IDLE_MAX_SECONDS", "IDLE_MAX_CEILING_SECONDS", "IdleBackoff", "idle_max_seconds"]
