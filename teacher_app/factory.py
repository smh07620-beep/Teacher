"""Production Flask application factory.

The factory composes canonical domain packages onto a fresh Flask object so
test/application instances do not share request hooks, extensions, or view-
function mutations.
"""

from __future__ import annotations

from flask import Flask, session

from teacher_app.config import STATIC_DIR, configure_app
from teacher_app.common.errors import register_error_handlers


def _register_production(app: Flask) -> Flask:
    """Apply the canonical production registration order in one place."""
    # Imports stay local so importing ``teacher_app`` does not eagerly import
    # every compatibility surface.
    from teacher_app.maintenance.backup_routes import register_backup_restore
    from teacher_app.courses.bundle_routes import register_course_bundle_72
    from teacher_app.courses.bundle_followup_routes import register_course_bundle_followup_73
    from teacher_app.courses.routes import register_course_routes
    from teacher_app.assessments.routes import register_assessment_routes
    from teacher_app.exams.routes import register_exam_integrity_guards
    from teacher_app.exams.record_routes import register_record_routes
    from teacher_app.materials.external_media_routes import register_external_media
    from teacher_app.materials.legacy_office import register_legacy_office_69
    from teacher_app.assessments.question_bank_routes import register_question_bank
    from teacher_app.assessments.question_runtime import build_canonical_question_runtime
    from teacher_app.auth.rbac_routes import register_rbac_681
    from teacher_app.maintenance.migrations import register_schema_migrations
    from teacher_app.maintenance import learning_assignment_migration as _learning_assignment_migration  # noqa: F401
    from teacher_app.maintenance import material_version_migration as _material_version_migration  # noqa: F401
    from teacher_app.maintenance import notification_state_migration as _notification_state_migration  # noqa: F401
    from teacher_app.maintenance import course_feedback_migration as _course_feedback_migration  # noqa: F401
    from teacher_app.maintenance import saved_learning_items_migration as _saved_learning_items_migration  # noqa: F401
    from teacher_app.maintenance import completion_certificate_migration as _completion_certificate_migration  # noqa: F401

    from teacher_app.atlas.routes import register_atlas_70
    from teacher_app.auth import service as auth_service
    from teacher_app.auth.account_routes import register_multi_role_66
    from teacher_app.auth.elevation import register_admin_elevation, register_sensitive_elevation
    from teacher_app.command_center.audience import register_training_audience_71
    from teacher_app.command_center.routes import register_training_command_center
    from teacher_app.command_center.dashboard_routes import register_dashboard_routes
    from teacher_app.command_center.notification_routes import register_notification_state_routes
    from teacher_app.common.audit_routes import register_general_audit_routes
    from teacher_app.common.privacy import register_ai_privacy
    from teacher_app.common.security import register_production_hardening
    from teacher_app.common import db as common_db
    from teacher_app.frontend.assets import register_pgy_frontend
    from teacher_app.frontend.cache_policy import register_browser_cache_policy
    from teacher_app.frontend.pages import register_page_routes
    from teacher_app.learning.routes import register_smart_learning
    from teacher_app.learning.progress_routes import register_progress_routes
    from teacher_app.learning.assignment_routes import register_learning_assignment_routes
    from teacher_app.learning.feedback_routes import register_course_feedback_routes
    from teacher_app.learning.saved_routes import register_saved_learning_routes
    from teacher_app.learning.calendar_routes import register_learning_calendar_routes
    from teacher_app.learning.compliance_routes import register_training_compliance_routes
    from teacher_app.learning.certificate_routes import register_completion_certificate_routes
    from teacher_app.maintenance.health import register_health
    from teacher_app.maintenance.announcement_routes import register_announcement_routes
    from teacher_app.materials.upload_routes import register_upload_hardening
    from teacher_app.materials.delivery_routes import register_material_delivery_routes
    from teacher_app.materials.routes import register_material_catalog_routes
    from teacher_app.materials.job_routes import register_material_job_routes
    from teacher_app.materials.job_runtime import build_canonical_runtime as build_material_job_runtime
    from teacher_app.materials import repository as material_repository
    from teacher_app.materials.template_routes import register_doc_template_routes
    from teacher_app.materials.sync_upload_routes import register_sync_upload_routes
    from teacher_app.storage.admin_routes import register_storage_admin_routes
    from teacher_app.storage import r2_ledger
    from teacher_app.worker.routes import register_free_worker
    from teacher_app.worker.web_runtime import build_canonical_runtime as build_worker_web_runtime
    from teacher_app.pgy.assessment_routes import register_pgy_assessment_routes

    app = register_schema_migrations(app)
    current_user = lambda: auth_service.current_user(session, include_roles=True)

    app = register_page_routes(app, static_dir=app.static_folder, current_user=current_user)
    app = register_material_delivery_routes(app, paths=app.config["STORAGE_PATHS"])
    app = register_material_catalog_routes(app, paths=app.config["STORAGE_PATHS"])
    app = register_material_job_routes(
        app,
        runtime=build_material_job_runtime(
            paths_provider=lambda: app.config["STORAGE_PATHS"],
        ),
    )
    app = register_doc_template_routes(
        app,
        paths=app.config["STORAGE_PATHS"],
        r2_record_object=r2_ledger.record_object,
    )
    app = register_sync_upload_routes(
        app,
        paths=app.config["STORAGE_PATHS"],
        r2_record_object=r2_ledger.record_object,
        r2_record_deleted=r2_ledger.record_deleted,
    )
    app = register_storage_admin_routes(
        app,
        paths=app.config["STORAGE_PATHS"],
        r2_record_object=r2_ledger.record_object,
        r2_record_deleted=r2_ledger.record_deleted,
    )
    app = register_course_routes(app)
    app = register_assessment_routes(app)
    app = register_record_routes(app)
    app = register_pgy_assessment_routes(app, paths=app.config["STORAGE_PATHS"])
    app = register_multi_role_66(app)
    app = register_general_audit_routes(app)
    app = register_training_audience_71(app)
    app = register_health(app, connection_factory=common_db.get_connection)
    app = register_training_command_center(app)
    app = register_dashboard_routes(app)
    app = register_notification_state_routes(app)
    app = register_exam_integrity_guards(app)
    app = register_production_hardening(app, current_user=current_user)
    app = register_upload_hardening(app)
    app = register_browser_cache_policy(app)
    app = register_ai_privacy(
        app,
        material_lookup=material_repository.get_material,
    )
    app = register_backup_restore(app, paths=app.config["STORAGE_PATHS"])
    smart_learning_paths = app.config["STORAGE_PATHS"]
    app = register_smart_learning(
        app,
        paths=smart_learning_paths,
        # Read the canonical app configuration dynamically so tests/runtime
        # composition can override StoragePaths without teaching the domain
        # layer about legacy module globals.
        paths_provider=lambda: app.config["STORAGE_PATHS"],
        material_getter=lambda material_id: material_repository.get_material(material_id),
    )
    app = register_progress_routes(app)
    app = register_learning_assignment_routes(app)
    app = register_course_feedback_routes(app)
    app = register_saved_learning_routes(app)
    app = register_learning_calendar_routes(app)
    app = register_training_compliance_routes(app)
    app = register_completion_certificate_routes(app)
    app = register_announcement_routes(app)
    app = register_free_worker(
        app,
        runtime=build_worker_web_runtime(
            paths_provider=lambda: app.config["STORAGE_PATHS"],
        ),
    )
    app = register_pgy_frontend(app)
    app = register_external_media(app)
    app = register_admin_elevation(app, current_user=current_user)
    app = register_rbac_681(app)
    app = register_course_bundle_72(app)
    app = register_course_bundle_followup_73(app)
    atlas_paths = app.config["STORAGE_PATHS"]

    app = register_atlas_70(
        app,
        paths=atlas_paths,
        paths_provider=lambda: app.config["STORAGE_PATHS"],
        material_getter=lambda material_id: material_repository.get_material(material_id),
    )
    app = register_sensitive_elevation(app)
    app = register_question_bank(
        app,
        runtime_question_runtime=build_canonical_question_runtime(
            paths_provider=lambda: app.config["STORAGE_PATHS"],
        ),
    )
    app = register_legacy_office_69(app)
    return app


def _register_canonical_blueprints(app: Flask) -> Flask:
    """Mount canonical auth/exam/PGY routes with production request bindings."""
    # Import route modules so their decorators have populated each blueprint.
    from teacher_app.auth import bp as auth_bp
    from teacher_app.auth import routes as _auth_routes  # noqa: F401
    from teacher_app.exams import bp as exams_bp
    from teacher_app.exams import routes as _exam_routes  # noqa: F401
    from teacher_app.pgy.routes import bp as pgy_bp
    from teacher_app.common.request_context import register_request_context

    register_request_context(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(exams_bp)
    app.register_blueprint(pgy_bp)
    return app


def create_app() -> Flask:
    from teacher_app.maintenance.bootstrap import run_bootstrap

    app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="")
    configure_app(app)
    app = run_bootstrap(app)
    app = _register_canonical_blueprints(app)
    app = _register_production(app)
    register_error_handlers(app)
    return app


__all__ = ["create_app"]
