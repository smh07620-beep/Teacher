"""Compatibility module alias for canonical maintenance migrations."""
import sys

from teacher_app.maintenance import migrations as _migrations
from teacher_app.maintenance import learning_assignment_migration as _learning_assignment_migration  # noqa: F401
from teacher_app.maintenance import material_version_migration as _material_version_migration  # noqa: F401
from teacher_app.maintenance import notification_state_migration as _notification_state_migration  # noqa: F401
from teacher_app.maintenance import course_feedback_migration as _course_feedback_migration  # noqa: F401
from teacher_app.maintenance import saved_learning_items_migration as _saved_learning_items_migration  # noqa: F401


sys.modules[__name__] = _migrations
