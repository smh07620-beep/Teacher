"""Deployment entrypoint that extends the existing Teacher app with Phase 3 PGY workflow.

Keeping the extension in a small entrypoint avoids destabilizing the large legacy
``app.py`` while still serving one Flask application in production.
"""
import app as legacy_app
from pgy_workflow import register_pgy_workflow
from pgy_frontend import register_pgy_frontend

app = register_pgy_workflow(legacy_app)
app = register_pgy_frontend(app)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
