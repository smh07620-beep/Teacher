"""Flask application factory for Teacher 6.5."""

from __future__ import annotations

from flask import Flask

from teacher_app.config import STATIC_DIR, configure_app
from teacher_app.common.errors import register_error_handlers


def register_blueprints(app: Flask) -> None:
    """Register modular blueprints.

    Auth, exams and PGY expose modular routes. Auth callers configure AUTH_BASE
    with their connection and area/group normalizers. The production legacy
    app uses explicit adapters and does not register these blueprints twice.
    """
    from teacher_app.admin.routes import bp as admin_bp
    from teacher_app.auth.routes import bp as auth_bp
    from teacher_app.exams.routes import bp as exams_bp
    from teacher_app.maintenance.routes import bp as maintenance_bp
    from teacher_app.materials.routes import bp as materials_bp
    from teacher_app.pgy.routes import bp as pgy_bp

    for blueprint in (auth_bp, exams_bp, pgy_bp, materials_bp, maintenance_bp, admin_bp):
        if blueprint.name not in app.blueprints:
            app.register_blueprint(blueprint)


def create_app() -> Flask:
    app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="")
    configure_app(app)
    register_blueprints(app)
    register_error_handlers(app)
    return app
