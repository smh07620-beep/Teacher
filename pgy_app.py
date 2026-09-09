"""Teacher 6.3 deployment entrypoint.

The legacy ``app.py`` remains the primary application. Phase 3/6.3 extensions
add PGY workflow, server-authoritative exams and production hardening without a
large invasive rewrite of the legacy file.
"""
import app as legacy_app
from exam_integrity import register_exam_integrity
from pgy_atomic import register_pgy_atomic_workflow
from pgy_frontend import register_pgy_frontend
from pgy_workflow import register_pgy_workflow
from production_hardening import register_production_hardening

app = register_pgy_workflow(legacy_app)
app = register_pgy_atomic_workflow(legacy_app)
app = register_exam_integrity(legacy_app)
app = register_production_hardening(legacy_app)
app = register_pgy_frontend(app)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
