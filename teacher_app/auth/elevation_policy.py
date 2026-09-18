"""Canonical path-to-permission policy for sensitive elevation checks."""
from __future__ import annotations


# Permission tuples mean that any listed permission may own the operation.
SENSITIVE_RULES = (
    ({"POST", "PUT", "PATCH", "DELETE"}, "/api/users", ("user.manage",)),
    ({"POST"}, "/api/storage/migrate-to-", ("storage.manage",)),
    ({"POST"}, "/api/maintenance/storage/mega/purge-root", ("system.manage",)),
    ({"POST"}, "/api/maintenance/restore", ("backup.manage", "education.cross_group.manage")),
    ({"GET"}, "/api/maintenance/backup", ("backup.manage", "education.cross_group.manage")),
    ({"DELETE"}, "/api/records", ("system.manage",)),
)


def required_permissions(method: str, path: str) -> tuple[str, ...]:
    method = str(method or "").upper()
    path = str(path or "")
    for methods, prefix, permissions in SENSITIVE_RULES:
        matches_path = (
            path == prefix
            or path.startswith(prefix + "/")
            or (prefix.endswith("-") and path.startswith(prefix))
        )
        if method in methods and matches_path:
            return permissions
    return ()


__all__ = ["SENSITIVE_RULES", "required_permissions"]
