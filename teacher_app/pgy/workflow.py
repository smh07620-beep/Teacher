"""Canonical PGY assignment state machine."""

from __future__ import annotations

import datetime as _dt
from typing import Optional

ASSIGNMENT_STATUSES = {
    "assigned",
    "submitted",
    "teacher_signed",
    "group_countersigned",
    "finalized",
    "cancelled",
}

# One action has exactly one expected source state, target state, and role.
# Reopen and cancel are administrative exceptions handled separately.
WORKFLOW_TRANSITIONS = {
    "submit": ("assigned", "submitted", "student"),
    "teacher_sign": ("submitted", "teacher_signed", "clinical_teacher"),
    "group_countersign": ("teacher_signed", "group_countersigned", "group_leader"),
    "finalize": ("group_countersigned", "finalized", "education_admin"),
}

REOPEN_SOURCE_STATUSES = {
    "submitted",
    "teacher_signed",
    "group_countersigned",
    "finalized",
}

CANCEL_BLOCKED_STATUSES = {"cancelled", "finalized"}

ADMIN_MUTATION_ROLES = {"education_admin"}
CANDIDATE_ROLES = {"education_admin", "group_leader"}
ASSIGNMENT_VIEW_ROLES = {"student", "clinical_teacher", "group_leader", "education_admin"}
AUDIT_VIEW_ROLES = {"auditor", "system_admin", "education_admin", "group_leader"}

# Match app.GROUPS so PGY code does not import the legacy Flask module.
KNOWN_GROUPS = {
    "grpBio",
    "grpMicro",
    "grpSero",
    "grpBB",
    "grpBact",
    "grpHema",
    "grpNew",
    "grpPgyDocs",
}
DEFAULT_GROUP = "grpBio"
SIGNATURE_ORDER = ["student", "clinical_teacher", "group_leader", "education_admin"]


def utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def normalize_group(value) -> str:
    return value if value in KNOWN_GROUPS else DEFAULT_GROUP


def transition_spec(action: str) -> Optional[tuple[str, str, str]]:
    return WORKFLOW_TRANSITIONS.get(str(action or ""))


def transition_allowed(status: str, action: str, role: str) -> bool:
    spec = transition_spec(action)
    if not spec:
        return False
    source, _target, required_role = spec
    return str(status or "") == source and str(role or "") == required_role


def required_role_for(action: str) -> str:
    spec = transition_spec(action)
    if not spec:
        raise KeyError(action)
    return spec[2]


def expected_status_for(action: str) -> str:
    spec = transition_spec(action)
    if not spec:
        raise KeyError(action)
    return spec[0]


def target_status_for(action: str) -> str:
    spec = transition_spec(action)
    if not spec:
        raise KeyError(action)
    return spec[1]


def actions_for_role(role: str) -> list[str]:
    actions = [name for name, (_src, _dst, required) in WORKFLOW_TRANSITIONS.items() if required == role]
    if role == "education_admin":
        actions.extend(["create", "edit_assignment", "reopen", "cancel"])
    return actions


def can_reopen(status: str) -> bool:
    return str(status or "") in REOPEN_SOURCE_STATUSES


def can_cancel(status: str) -> bool:
    return str(status or "") not in CANCEL_BLOCKED_STATUSES
