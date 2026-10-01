"""Canonical Teacher worker protocol domain.

The executable local worker remains ``material_worker.py``.  Modules in this
package own Web-side protocol state only; they must not start a second worker
loop or import provider credentials.
"""
from teacher_app.worker.protocol_version import (
    MATERIAL_WORKER_PROTOCOL_VERSION,
    MIN_MATERIAL_WORKER_PROTOCOL_VERSION,
    install_web_guards,
)


# Keep normal Web releases independent from the hospital Worker.  Only an
# incompatible wire-protocol version prevents queue claims.
install_web_guards()


__all__ = [
    "MATERIAL_WORKER_PROTOCOL_VERSION",
    "MIN_MATERIAL_WORKER_PROTOCOL_VERSION",
]
