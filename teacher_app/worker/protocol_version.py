"""Material Worker protocol-version negotiation and compatibility guards.

Normal Web/UI releases must not force the hospital Worker to update.  This
module only blocks queue claims when the Worker/Web wire protocol is actually
incompatible.  Heartbeats continue so operators can see the Worker and the
reason work is intentionally staying queued.
"""
from __future__ import annotations

from typing import Any, Mapping


MATERIAL_WORKER_PROTOCOL_VERSION = 2
MIN_MATERIAL_WORKER_PROTOCOL_VERSION = 2


def _protocol_version(capabilities: Any) -> int:
    payload = capabilities if isinstance(capabilities, Mapping) else {}
    try:
        return max(0, int(payload.get("protocolVersion", 0) or 0))
    except (TypeError, ValueError):
        return 0


def install_capability(worker_module: Any) -> None:
    """Advertise the current wire protocol on canonical Worker capabilities."""
    original = getattr(worker_module, "capability", None)
    if not callable(original) or getattr(original, "_teacher_protocol_versioned", False):
        return

    def versioned_capability():
        payload = dict(original() or {})
        payload["protocolVersion"] = MATERIAL_WORKER_PROTOCOL_VERSION
        return payload

    versioned_capability._teacher_protocol_versioned = True
    worker_module.capability = versioned_capability


def install_web_guards() -> None:
    """Install one idempotent claim gate plus status projection.

    The HTTP claim route persists a heartbeat before it calls the repository
    claim function.  That lets this guard reject an old protocol without
    changing the legacy route, consuming an attempt, or moving a job into
    retry_wait.  Repository callers that have no heartbeat remain unchanged.
    """
    from teacher_app.worker import operations, repository

    current_claim = repository.claim_next_material_job
    if not getattr(current_claim, "_teacher_protocol_guarded", False):
        original_claim = current_claim

        def guarded_claim_next_material_job(
            worker_id: str,
            *,
            now: str,
            connection_factory=None,
        ):
            heartbeat = None
            try:
                for item in repository.list_heartbeats(
                    50, connection_factory=connection_factory
                ):
                    if str(item.get("worker_id") or item.get("workerId") or "") == str(worker_id):
                        heartbeat = item
                        break
            except Exception:
                # A status lookup failure must not create a second queue outage.
                heartbeat = None
            if heartbeat is not None:
                version = _protocol_version(heartbeat.get("capabilities"))
                if version < MIN_MATERIAL_WORKER_PROTOCOL_VERSION:
                    return None
            return original_claim(
                worker_id,
                now=now,
                connection_factory=connection_factory,
            )

        guarded_claim_next_material_job._teacher_protocol_guarded = True
        repository.claim_next_material_job = guarded_claim_next_material_job

    current_status = operations.status
    if not getattr(current_status, "_teacher_protocol_projected", False):
        original_status = current_status

        def protocol_aware_status(staging_capability, *, connection_factory=None):
            data = original_status(
                staging_capability,
                connection_factory=connection_factory,
            )
            heartbeat_map = {}
            try:
                heartbeat_map = {
                    str(item.get("worker_id") or item.get("workerId") or ""): item
                    for item in repository.list_heartbeats(
                        50, connection_factory=connection_factory
                    )
                }
            except Exception:
                heartbeat_map = {}
            for worker in data.get("workers", []):
                item = heartbeat_map.get(str(worker.get("workerId") or ""), {})
                version = _protocol_version(item.get("capabilities"))
                worker["protocolVersion"] = version
                worker["minimumProtocolVersion"] = MIN_MATERIAL_WORKER_PROTOCOL_VERSION
                worker["protocolCompatible"] = version >= MIN_MATERIAL_WORKER_PROTOCOL_VERSION
                worker["updateRequired"] = not worker["protocolCompatible"]
            data["minimumWorkerProtocolVersion"] = MIN_MATERIAL_WORKER_PROTOCOL_VERSION
            return data

        protocol_aware_status._teacher_protocol_projected = True
        operations.status = protocol_aware_status


__all__ = [
    "MATERIAL_WORKER_PROTOCOL_VERSION",
    "MIN_MATERIAL_WORKER_PROTOCOL_VERSION",
    "install_capability",
    "install_web_guards",
]
