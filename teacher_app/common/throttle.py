"""Process-local throttle for best-effort housekeeping callbacks.

The material Worker asks the Web app for work every ~2 seconds.  Housekeeping
that rides along with every claim (R2 reservation cleanup, staging cleanup)
re-read whole tables from the database each time, which became a major source
of Supabase egress.  Housekeeping does not need 2-second freshness, so wrap it
with :func:`throttled` and run it at most once per interval per process.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any, Callable

DEFAULT_CLEANUP_INTERVAL_SECONDS = 300


def cleanup_interval_seconds() -> float:
    """Seconds between housekeeping runs (``MATERIAL_CLEANUP_INTERVAL_SECONDS``).

    ``0`` disables throttling (every call runs), which tests and emergency
    debugging can use.  Values are clamped to 0..3600; garbage falls back to
    the default.
    """
    raw = os.environ.get("MATERIAL_CLEANUP_INTERVAL_SECONDS")
    if raw is None or str(raw).strip() == "":
        return float(DEFAULT_CLEANUP_INTERVAL_SECONDS)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return float(DEFAULT_CLEANUP_INTERVAL_SECONDS)
    return max(0.0, min(3600.0, value))


def throttled(
    func: Callable[..., Any],
    *,
    interval_seconds: float | Callable[[], float] = cleanup_interval_seconds,
    clock: Callable[[], float] = time.monotonic,
) -> Callable[..., Any]:
    """Return ``func`` wrapped so it runs at most once per interval.

    The first call always runs.  Calls inside the interval return ``None``
    without touching ``func``.  The interval starts when a run *starts*, so a
    failing housekeeping callback is not retried on every 2-second claim; its
    exception still propagates to that one caller exactly as before.
    """
    lock = threading.Lock()
    state: dict[str, float | None] = {"last": None}

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        interval = interval_seconds() if callable(interval_seconds) else float(interval_seconds)
        now = clock()
        with lock:
            last = state["last"]
            if interval > 0 and last is not None and now - last < interval:
                return None
            state["last"] = now
        return func(*args, **kwargs)

    return wrapper


__all__ = ["DEFAULT_CLEANUP_INTERVAL_SECONDS", "cleanup_interval_seconds", "throttled"]
