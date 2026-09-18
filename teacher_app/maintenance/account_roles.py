"""Explicit account-role maintenance commands.

Operational account changes belong here instead of Flask application startup.
The module uses the canonical database transaction seam and can be invoked with
``python -m teacher_app.maintenance.account_roles grant-system-admin USERNAME``.
"""
from __future__ import annotations

import argparse
import json
from contextlib import contextmanager
from typing import Any, Callable, Iterator

from teacher_app.common import db as common_db
from teacher_app.common.auth import normalize_roles


ConnectionFactory = Callable[[], tuple[Any, str]]


@contextmanager
def _transaction(
    connection_factory: ConnectionFactory | None = None,
) -> Iterator[tuple[Any, str]]:
    if connection_factory is None:
        with common_db.transaction() as pair:
            yield pair
        return

    conn, kind = connection_factory()
    try:
        if kind == "postgres":
            transaction = getattr(conn, "transaction", None)
            if callable(transaction):
                with transaction():
                    yield conn, kind
            else:
                yield conn, kind
            return

        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn, kind
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()
    finally:
        conn.close()


def grant_system_admin(
    username: str,
    *,
    connection_factory: ConnectionFactory | None = None,
) -> bool:
    """Add ``system_admin`` to one existing account and make it primary.

    Passwords and unrelated profile fields are never modified. Missing accounts
    return ``False`` so operations can fail safely without creating identities.
    """
    username = str(username or "").strip()
    if not username:
        raise ValueError("username is required")

    with _transaction(connection_factory) as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT username,role,roles_json FROM user_accounts WHERE username={ph}",
            (username,),
        ).fetchone()
        if not row:
            return False

        current = dict(row)
        roles = normalize_roles(current.get("roles_json"), primary=current.get("role"))
        roles = ["system_admin"] + [role for role in roles if role != "system_admin"]
        if current.get("role") == "system_admin" and normalize_roles(
            current.get("roles_json"), primary=current.get("role")
        ) == roles:
            return True

        conn.execute(
            f"UPDATE user_accounts SET role={ph},roles_json={ph} WHERE username={ph}",
            (
                "system_admin",
                json.dumps(roles, ensure_ascii=False, separators=(",", ":")),
                username,
            ),
        )
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Teacher account-role maintenance")
    subcommands = parser.add_subparsers(dest="command", required=True)
    grant = subcommands.add_parser("grant-system-admin")
    grant.add_argument("username")
    args = parser.parse_args(argv)

    if args.command == "grant-system-admin":
        changed = grant_system_admin(args.username)
        if not changed:
            parser.error(f"account not found: {args.username}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["grant_system_admin", "main"]
