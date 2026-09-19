"""Legacy import adapter for canonical PGY compatibility routes."""
from teacher_app.pgy import routes_legacy as _routes

ASSIGNMENT_STATUSES = _routes.ASSIGNMENT_STATUSES
WORKFLOW_TRANSITIONS = _routes.WORKFLOW_TRANSITIONS
transition_allowed = _routes.transition_allowed
utcnow = _routes.utcnow
_json_load = _routes._json_load
_json_dump = _routes._json_dump
_username = _routes._username
_text = _routes._text
_ph = _routes._ph
_role = _routes._role
_user_group = _routes._user_group
_auth = _routes._auth
init_pgy_workflow_db = _routes.init_pgy_workflow_db
_lookup_account = _routes._lookup_account
_course_row = _routes._course_row
_assignment_query = _routes._assignment_query
_assignment_dict = _routes._assignment_dict
_get_assignment = _routes._get_assignment
_can_view = _routes._can_view
_audit = _routes._audit
_legacy_error_body = _routes._legacy_error_body
_legacy_error = _routes._legacy_error
_assignment_response = _routes._assignment_response
register_pgy_workflow = _routes.register_pgy_workflow

__all__ = ["register_pgy_workflow"]
