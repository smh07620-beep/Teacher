"""Account persistence through the existing SQLite/PostgreSQL connection seam.

No schema creation or database connection occurs on import.
"""

from teacher_app.common.db import get_connection, placeholder


def _connection(base):
    return base._db_conn() if base is not None else get_connection()


def find_user(base, username):
    conn, kind = _connection(base)
    try:
        row = conn.execute(
            f"SELECT * FROM user_accounts WHERE username={placeholder(kind)}",
            (username,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def record_login(base, username, timestamp):
    conn, kind = _connection(base)
    try:
        ph = placeholder(kind)
        conn.execute(
            f"UPDATE user_accounts SET last_login_at={ph} WHERE username={ph}",
            (timestamp, username),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
