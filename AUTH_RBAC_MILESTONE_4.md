# Teacher 6.5 Milestone 4: Auth and centralized RBAC

The production entrypoint remains `pgy_app:app` and `VERSION` remains `6.4.0`.
No migration or production data update is part of this milestone.

`app.py` retains its original auth implementations as `_legacy_*` functions.
The existing `api_auth_login`, `api_auth_me`, `api_auth_logout`, `_current_user`,
`_user_public`, `_normalize_username` and `require_roles` names now delegate to
the auth service or HTTP adapters. URL rules and endpoint names are unchanged.
User administration remains legacy and its session-version increments continue
to invalidate sessions after password changes or deactivation.

`teacher_app/common/auth.py` owns canonical roles, aliases, permissions and
role/permission guards. Both legacy and modular callers use that policy.
Only clinical teachers (including the `teacher` alias) have `evaluation.sign`;
system and education administrators cannot sign clinical evaluations.

`teacher_app/auth/repository.py` accesses the existing account table through
the supplied `_db_conn` connection. `service.py` checks passwords, projects public
user fields, records login times and validates sessions. `routes.py` preserves
legacy JSON bodies and status codes without adding new error-envelope fields.
Factory users set `app.config['AUTH_BASE']` to an object exposing `_db_conn`,
`normalize_area`, `normalize_group`, `DEFAULT_TRAINING_AREA`, and `DEFAULT_GROUP`.
The production app supplies itself explicitly.

Rate limiting and same-origin validation remain in `production_hardening.py`.
This retains the existing process-local failure counter and 429/Retry-After
contract; it does not add a second limiter or a distributed limiter.

Validation: `python -m unittest discover -s tests -v` runs all 75 tests,
including the existing 52 Milestone 1-3 / 6.4 tests and 23 auth/RBAC tests.
Auth tests use disposable SQLite databases, exercise the actual legacy adapter
functions, compare retained implementations, and check PostgreSQL placeholders
with a connection double. Live PostgreSQL integration is not part of this suite.
CI also compiles the Python package, checks browser scripts and loads the
unchanged production entrypoint.
