"""Compatibility module alias for canonical maintenance migrations."""
import sys

from teacher_app.maintenance import migrations as _migrations
from teacher_app.maintenance import learning_assignment_migration as _learning_assignment_migration  # noqa: F401
from teacher_app.maintenance import material_version_migration as _material_version_migration  # noqa: F401
from teacher_app.maintenance import notification_state_migration as _notification_state_migration  # noqa: F401
from teacher_app.maintenance import course_feedback_migration as _course_feedback_migration  # noqa: F401
from teacher_app.maintenance import saved_learning_items_migration as _saved_learning_items_migration  # noqa: F401
from teacher_app.maintenance import completion_certificate_migration as _completion_certificate_migration  # noqa: F401
from teacher_app.maintenance import account_email_migration as _account_email_migration  # noqa: F401
from teacher_app.maintenance import media_script_migration as _media_script_migration  # noqa: F401
from teacher_app.maintenance import media_audio_migration as _media_audio_migration  # noqa: F401
from teacher_app.maintenance import content_audience_migration as _content_audience_migration  # noqa: F401
from teacher_app.maintenance import ai_material_migration as _ai_material_migration  # noqa: F401
from teacher_app.maintenance import media_subtitle_migration as _media_subtitle_migration  # noqa: F401
from teacher_app.maintenance import ai_presentation_migration as _ai_presentation_migration  # noqa: F401
from teacher_app.maintenance import ai_video_migration as _ai_video_migration  # noqa: F401
from teacher_app.maintenance import ai_presentation_phase2_migration as _ai_presentation_phase2_migration  # noqa: F401
from teacher_app.maintenance import ai_presentation_phase3_migration as _ai_presentation_phase3_migration  # noqa: F401
from teacher_app.maintenance import ai_presentation_phase4_migration as _ai_presentation_phase4_migration  # noqa: F401
from teacher_app.maintenance import notification_preference_migration as _notification_preference_migration  # noqa: F401
from teacher_app.maintenance import material_job_progress_migration as _material_job_progress_migration  # noqa: F401
from teacher_app.maintenance import operational_incident_migration as _operational_incident_migration  # noqa: F401
from teacher_app.maintenance import operational_incident_response_migration as _operational_incident_response_migration  # noqa: F401
from teacher_app.maintenance import operational_metrics_migration as _operational_metrics_migration  # noqa: F401
from teacher_app.maintenance import forecast_prediction_migration as _forecast_prediction_migration  # noqa: F401
from teacher_app.maintenance import email_delivery_migration as _email_delivery_migration  # noqa: F401
from teacher_app.maintenance import course_lifecycle_migration as _course_lifecycle_migration  # noqa: F401
from teacher_app.maintenance import training_intervention_migration as _training_intervention_migration  # noqa: F401
from teacher_app.maintenance import material_derivative_migration as _material_derivative_migration  # noqa: F401
from teacher_app.maintenance import announcement_audience_migration as _announcement_audience_migration  # noqa: F401
from teacher_app.maintenance import exam_assignee_migration as _exam_assignee_migration  # noqa: F401
from teacher_app.maintenance import slide_checkpoint_migration as _slide_checkpoint_migration  # noqa: F401


sys.modules[__name__] = _migrations