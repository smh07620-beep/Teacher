"""Account self-service, password-reset and reminder schema."""
from teacher_app.maintenance.migrations import migration

@migration("0093-account-email-security")
def account_email_security_93(conn, kind: str) -> None:
    boolean = "BOOLEAN" if kind == "postgres" else "INTEGER"
    default_true = "TRUE" if kind == "postgres" else "1"
    # Additive account fields.
    existing = set()
    if kind == "postgres":
        rows=conn.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='user_accounts'").fetchall()
        existing={str(dict(r).get("column_name","")) for r in rows}
    else:
        existing={str(r[1]) for r in conn.execute("PRAGMA table_info(user_accounts)").fetchall()}
    for name, ddl in {
        "email":"TEXT NOT NULL DEFAULT ''",
        "email_notifications":f"{boolean} NOT NULL DEFAULT {default_true}",
    }.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE user_accounts ADD COLUMN {name} {ddl}")
    # Existing staff accounts default to the institutional mailbox derived
    # from the authoritative employee id. Never overwrite an explicit email.
    # Very old backup schemas can predate emp_id, so backfill only when that
    # authoritative source column is actually present.
    if "emp_id" in existing:
        conn.execute("""UPDATE user_accounts
            SET email = LOWER(TRIM(emp_id)) || '@smh.org.tw'
            WHERE (email IS NULL OR TRIM(email) = '')
              AND emp_id IS NOT NULL AND TRIM(emp_id) <> ''""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_accounts_email ON user_accounts(email)")
    conn.execute("""CREATE TABLE IF NOT EXISTS password_reset_tokens (
        token_hash TEXT PRIMARY KEY, username TEXT NOT NULL, created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL, used_at TEXT NOT NULL DEFAULT ''
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_password_reset_user ON password_reset_tokens(username,expires_at)")
    conn.execute("""CREATE TABLE IF NOT EXISTS email_notification_log (
        id TEXT PRIMARY KEY, username TEXT NOT NULL, notification_key TEXT NOT NULL,
        kind TEXT NOT NULL, sent_at TEXT NOT NULL, UNIQUE(username,notification_key)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS exam_windows (
        quiz_category_id TEXT PRIMARY KEY, opens_at TEXT NOT NULL DEFAULT '',
        closes_at TEXT NOT NULL DEFAULT '', reminder_enabled """+boolean+""" NOT NULL DEFAULT """+default_true+""",
        updated_at TEXT NOT NULL, updated_by TEXT NOT NULL DEFAULT ''
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_exam_windows_close ON exam_windows(closes_at)")

__all__=["account_email_security_93"]
