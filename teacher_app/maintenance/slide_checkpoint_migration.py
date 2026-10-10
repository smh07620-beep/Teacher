"""Optional in-slide checkpoint questions (teacher opt-in, additive only)."""
from teacher_app.maintenance.migrations import migration


@migration("0118-slide-checkpoints")
def slide_checkpoints_118(conn, kind: str) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS slide_checkpoints (
        id TEXT PRIMARY KEY,
        material_id TEXT NOT NULL,
        material_version INTEGER NOT NULL DEFAULT 1,
        group_key TEXT NOT NULL DEFAULT '',
        page_no INTEGER NOT NULL,
        question TEXT NOT NULL,
        options_json TEXT NOT NULL DEFAULT '[]',
        correct_index INTEGER NOT NULL DEFAULT 0,
        explanation TEXT NOT NULL DEFAULT '',
        active INTEGER NOT NULL DEFAULT 1,
        created_by TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT '',
        updated_by TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT ''
    )""")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_slide_checkpoints_material "
        "ON slide_checkpoints(material_id, page_no)"
    )
    conn.execute("""CREATE TABLE IF NOT EXISTS slide_checkpoint_answers (
        checkpoint_id TEXT NOT NULL,
        username TEXT NOT NULL,
        material_id TEXT NOT NULL DEFAULT '',
        chosen_index INTEGER NOT NULL,
        is_correct INTEGER NOT NULL DEFAULT 0,
        answered_at TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (checkpoint_id, username)
    )""")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_slide_checkpoint_answers_user "
        "ON slide_checkpoint_answers(username, material_id)"
    )
