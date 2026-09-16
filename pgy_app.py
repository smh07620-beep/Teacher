"""Teacher 6.6 deployment entrypoint.

The legacy ``app.py`` remains the primary application. Phase 3 workflow and
modular exam-integrity adapters stay intact while 6.6 adds the formal additive
RBAC/PGY signing migration on top of the 6.4 protection controls.
"""
import app as legacy_app
from ai_privacy import register_ai_privacy
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
from teacher_app.assessments.routes import register_legacy_assessment_routes
from teacher_app.courses.routes import register_legacy_course_routes
from teacher_app.materials.routes import register_legacy_material_routes

app = register_pgy_workflow(legacy_app)
# Importing the Course Wizard adapters above registers their additive migrations
# before the migration runner executes.
app = register_schema_migrations(legacy_app)
app = register_multi_role_66(legacy_app)
app = register_health(legacy_app)
app = register_pgy_atomic_workflow(legacy_app)
app = register_pgy_signing_66(legacy_app)
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
