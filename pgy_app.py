"""Teacher 6.4 deployment entrypoint.

The legacy ``app.py`` remains the primary application. Phase 3/6.3 workflow and
exam-integrity extensions stay intact while 6.4 adds explicit migrations,
logical backup/restore, upload signature validation and AI de-identification.
"""
import app as legacy_app
from ai_privacy import register_ai_privacy
from backup_restore import register_backup_restore
from exam_integrity import register_exam_integrity
from pgy_atomic import register_pgy_atomic_workflow
from pgy_frontend import register_pgy_frontend
from pgy_workflow import register_pgy_workflow
from production_hardening import register_production_hardening
from schema_migrations import register_schema_migrations
from upload_hardening import register_upload_hardening

app = register_schema_migrations(legacy_app)
app = register_pgy_workflow(legacy_app)
app = register_pgy_atomic_workflow(legacy_app)
app = register_exam_integrity(legacy_app)
# Register same-origin/rate-limit checks before upload parsing/validation.
app = register_production_hardening(legacy_app)
app = register_upload_hardening(legacy_app)
app = register_ai_privacy(legacy_app)
app = register_backup_restore(legacy_app)
app = register_pgy_frontend(app)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
