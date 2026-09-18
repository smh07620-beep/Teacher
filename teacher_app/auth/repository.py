"""Canonical account persistence on the shared Teacher database seam.

No schema creation or database connection occurs on import.
"""

from collections.abc import Mapping

from teacher_app.common import db as common_db


def find_user(username):
    with common_db.read_connection() as (conn, kind):
        row = conn.execute(
            f"SELECT * FROM user_accounts WHERE username={common_db.placeholder(kind)}",
            (username,),
        ).fetchone()
    return dict(row) if row else None


def record_login(username, timestamp):
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        conn.execute(
            f"UPDATE user_accounts SET last_login_at={ph} WHERE username={ph}",
            (timestamp, username),
        )


def list_users():
    with common_db.read_connection() as (conn, _kind):
        rows = conn.execute(
            "SELECT * FROM user_accounts "
            "ORDER BY active DESC, display_name ASC, username ASC"
        ).fetchall()
    return [dict(row) for row in rows]


def profile_columns_available() -> bool:
    with common_db.read_connection() as (conn, kind):
        if kind == "postgres":
            rows = conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema=current_schema() AND table_name='user_accounts'"
            ).fetchall()
            columns = {str(dict(row).get("column_name", "")) for row in rows}
        else:
            columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(user_accounts)").fetchall()}
        return {"professional_title", "responsibility_tags"}.issubset(columns)


def create_user(values: Mapping[str, object]) -> dict:
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        columns = list(values)
        params = [
            bool(values[column]) if column == "active" and kind == "postgres"
            else int(bool(values[column])) if column == "active"
            else values[column]
            for column in columns
        ]
        conn.execute(
            f"INSERT INTO user_accounts ({','.join(columns)}) "
            f"VALUES ({','.join([ph] * len(columns))})",
            params,
        )
        row = conn.execute(
            f"SELECT * FROM user_accounts WHERE username={ph}",
            (values["username"],),
        ).fetchone()
    return dict(row)


def update_user(
    username: str,
    updates: Mapping[str, object],
    *,
    invalidate_session: bool = False,
) -> dict | None:
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        fields = []
        params = []
        for column, value in updates.items():
            fields.append(f"{column}={ph}")
            if column == "active":
                value = bool(value) if kind == "postgres" else int(bool(value))
            params.append(value)
        if invalidate_session:
            fields.append("session_version=session_version+1")
        if fields:
            params.append(username)
            conn.execute(
                f"UPDATE user_accounts SET {','.join(fields)} WHERE username={ph}",
                params,
            )
        row = conn.execute(
            f"SELECT * FROM user_accounts WHERE username={ph}",
            (username,),
        ).fetchone()
    return dict(row) if row else None
