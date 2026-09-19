"""Legacy registration adapter for canonical production security hooks."""
from __future__ import annotations

import time

from teacher_app.common import security

_RATE_LOCK = security._RATE_LOCK
_LOGIN_FAILURES = security._LOGIN_FAILURES
_truthy = security.truthy
_client_ip = security.client_ip
_login_key = security.login_key
_same_origin = security.same_origin
_csrf_origin_ok = security.csrf_origin_ok


def register_production_hardening(base):
    return security.register_production_hardening(
        base.app,
        current_user=base._current_user,
        login_failures=_LOGIN_FAILURES,
        rate_lock=_RATE_LOCK,
        clock=time,
    )


__all__ = ["register_production_hardening"]
