"""Canonical pre-migration production bootstrap.

Fresh installations need a small set of base tables before the release
migration registry can apply additive migrations.  Ownership lives in domain
packages; this module only coordinates their startup order and historical data
migrations.
"""
from __future__ import annotations

from teacher_app.assessments import schema as assessment_schema
from teacher_app.common import db as common_db
from teacher_app.courses import schema as course_schema
from teacher_app.exams import schema as exam_schema
from teacher_app.learning import schema as learning_schema
from teacher_app.maintenance import announcement_schema, legacy_data_migrations
from teacher_app.materials import schema as material_schema
from teacher_app.materials import templates as material_templates
from teacher_app.pgy import assessments as pgy_assessments
from teacher_app.pgy import repository as pgy_repository
from teacher_app.worker import schema as worker_schema


PRE_MIGRATION_SCHEMA_OWNERS = (
    exam_schema.init_schema,
    material_schema.init_schema,
    assessment_schema.init_schema,
    worker_schema.init_schema,
    course_schema.init_schema,
    learning_schema.init_schema,
    announcement_schema.init_schema,
    pgy_repository.init_schema,
)


ALIGN_MATERIAL_SCOPE_SQL = (
    "UPDATE materials SET "
    "group_key=(SELECT c.group_key FROM courses c WHERE c.id=materials.course_id), "
    "training_area=(SELECT c.training_area FROM courses c WHERE c.id=materials.course_id) "
    "WHERE course_id<>'' AND EXISTS (SELECT 1 FROM courses c WHERE c.id=materials.course_id "
    "AND (c.group_key<>materials.group_key OR c.training_area<>materials.training_area))"
)


def align_material_scope_to_courses(conn) -> None:
    """A material attached to a course belongs to that course's group/area.

    Idempotent: only rows that disagree with their course are touched.
    """
    try:
        conn.execute(ALIGN_MATERIAL_SCOPE_SQL)
        conn.commit()
    except Exception:  # best effort; never block startup
        try:
            conn.rollback()
        except Exception:
            pass


def run_bootstrap(app, *, connection_factory=None):
    """Establish canonical base schemas and one-time historical data state."""
    if app.extensions.get("teacher_bootstrap_completed"):
        return app

    factory = connection_factory or common_db.get_connection
    conn, kind = factory()
    try:
        for init_schema in PRE_MIGRATION_SCHEMA_OWNERS:
            init_schema(conn, kind)
        align_material_scope_to_courses(conn)
    finally:
        conn.close()

    # These package owners expose connection-factory public APIs because their
    # runtime repositories also initialize the same tables in focused tests.
    material_templates.init_schema(factory)
    pgy_assessments.init_schema(factory)

    # Seed historical built-ins only after the quiz baseline exists.  The
    # V5.4 compatibility migration intentionally runs after the seed so those
    # historical quizzes retain the original draw-count behavior.
    legacy_data_migrations.run_legacy_data_migrations(factory)

    app.extensions["teacher_bootstrap_completed"] = True
    return app


__all__ = ["PRE_MIGRATION_SCHEMA_OWNERS", "run_bootstrap"]
