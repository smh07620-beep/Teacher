"""Teacher deployment entrypoint.

The legacy ``app.py`` remains the primary application while canonical Teacher
modules own the converged domains and compatibility adapters preserve routes.
"""
import app as legacy_app
from ai_privacy import register_ai_privacy
from assessment_performance_712 import register_assessment_performance_712
from backup_restore import register_backup_restore
from course_bundle_72 import register_course_bundle_72
from course_bundle_followup_73 import register_course_bundle_followup_73
from exam_integrity import register_exam_integrity
from free_worker_67 import register_free_worker
from health_65 import register_health
from multi_role_66 import register_multi_role_66
from pgy_atomic import register_pgy_atomic_workflow
from pgy_signing_66 import register_pgy_signing_66
from pgy_frontend import register_pgy_frontend
from pgy_workflow import register_pgy_workflow
from production_hardening import register_production_hardening
from schema_migrations import register_schema_migrations
from smart_learning_67 import register_smart_learning
from upload_hardening import register_upload_hardening
from external_media_68 import register_external_media
from admin_elevation_68 import register_admin_elevation
from question_bank_68 import register_question_bank
from rbac_681 import register_rbac_681
from legacy_office_69 import register_legacy_office_69
from sensitive_elevation_69 import register_sensitive_elevation_69
from atlas_70 import register_atlas_70
from storage_pagination_hardening import install_storage_pagination_hardening
from teacher_app.assessments.routes import register_legacy_assessment_routes
from teacher_app.command_center.audience import register_training_audience_71
from teacher_app.command_center.routes import register_training_command_center
from teacher_app.courses.routes import register_legacy_course_routes
from teacher_app.materials.routes import register_legacy_material_routes

# Keep legacy storage ownership in app.py, but replace its S3-compatible
# pagination loops before any route can invoke them. The wrappers fail closed
# on missing/repeated continuation tokens instead of spinning forever.
install_storage_pagination_hardening(legacy_app)

app = register_pgy_workflow(legacy_app)
# Importing the adapters above registers additive migrations before the runner.
app = register_schema_migrations(legacy_app)
# Teacher 7.12 keeps canonical auth semantics but avoids repeating the same
# Supabase user lookup inside one request and adds assessment-list indexes.
app = register_assessment_performance_712(legacy_app)
app = register_multi_role_66(legacy_app)
# Teacher 7.1 audience is an explicit training-track flag. It does not grant
# RBAC, signing, or administrative authority.
app = register_training_audience_71(legacy_app)
app = register_health(legacy_app)
app = register_pgy_atomic_workflow(legacy_app)
app = register_pgy_signing_66(legacy_app)
# Teacher 7.1 command center is a read-only aggregation surface over canonical
# domains. It owns no mutation rules and never replaces professional signers.
app = register_training_command_center(legacy_app)
app = register_exam_integrity(legacy_app)
# Stage 5.1 moves the live materials/course/assessment controller behavior to
# canonical teacher_app modules while retaining every legacy URL rule. Register
# before RBAC and later compatibility overlays so those wrappers protect the
# canonical handlers rather than the retired app.py implementations.
app = register_legacy_material_routes(legacy_app)
app = register_legacy_course_routes(legacy_app)
app = register_legacy_assessment_routes(legacy_app)
# Register same-origin/rate-limit checks before upload parsing/validation.
app = register_production_hardening(legacy_app)
app = register_upload_hardening(legacy_app)
app = register_ai_privacy(legacy_app)
app = register_backup_restore(legacy_app)
app = register_smart_learning(legacy_app)
app = register_free_worker(legacy_app)
app = register_pgy_frontend(app)
app = register_external_media(legacy_app)
app = register_admin_elevation(legacy_app)
app = register_rbac_681(legacy_app)
# Course bundle creation and its material follow-ups are ordinary teaching
# workflows. Canonical session RBAC/group scope are established first.
app = register_course_bundle_72(legacy_app)
app = register_course_bundle_followup_73(legacy_app)
app = register_atlas_70(legacy_app)
# Sensitive account/storage/backup/destructive system actions add a short-lived
# elevation check on top of canonical RBAC. Normal teacher work never enters it.
app = register_sensitive_elevation_69(legacy_app)
app = register_question_bank(legacy_app)
# Register after RBAC so the legacy Office route uses canonical scoped
# authorization and can never fall through to the original source handler.
app = register_legacy_office_69(legacy_app)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
