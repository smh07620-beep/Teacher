# Root mirror cleanup — phase 1 inventory and freeze

## Purpose and boundary

This document is the ownership record for the first, deliberately small, stale-root-mirror cleanup.  Production remains **`pgy_app:app`**.  `app.py` is not deleted and remains the compatibility host while routes are progressively moved behind canonical modules.

The rule is simple: when a domain has a canonical `teacher_app/` owner, new business rules, authorization decisions, persistence behavior, and HTTP semantics belong there.  A root file may keep a route name, legacy response shape, registration call, or narrowly scoped adapter only.  It must not become a second implementation.

This phase makes no database migration, Render change, version change, or production-entrypoint change.

## Completed stale frontend mirror removal

`static/` is the sole canonical web-asset directory: the Flask application is
configured with `STATIC_DIR = BASE_DIR / "static"` and every public page route
uses that directory.  The former root copies of the following same-named
assets have therefore been removed.  They were stale mirrors, not fallback
assets or production entrypoints:

- HTML: `index.html`, `area-internal.html`, `area-pgy.html`, `login.html`, and
  `system.html`
- JavaScript: `login.js`, `portal-v56.js`, `shared-core.js`, `system-admin.js`,
  `system-assessment.js`, `system-bootstrap.js`, `system-core.js`,
  `system-exam.js`, `system-learner.js`, and `teaching.js`
- CSS: `admin.css`, `design-tokens.css`, `learner.css`, `phase3.css`,
  `portal-v56.css`, `portal-v571.css`, `portal.css`, `teaching.css`, `v561.css`,
  `v573.css`, `v574.css`, `v575.css`, and `v580.css`

Do not recreate a root copy of a file that is served from `static/`.  A new
root/static same-name pair requires an explicit compatibility decision and a
corresponding policy-test update.  The deferred Python modules in the
ownership matrix remain intentionally untouched because each still has unique
production behavior.

## Canonical ownership matrix

| Domain | Canonical owner | Root compatibility surface | Status / remaining debt |
| --- | --- | --- | --- |
| Auth and session lifecycle | `teacher_app.auth.service`, `repository`, `routes` | `app.py` calls the modular route/service functions; `_legacy_*` auth functions are test-only contract fixtures | **Frozen / converged.** Keep old URLs and JSON contracts; do not add auth logic to `app.py`. |
| RBAC, canonical roles, permissions | `teacher_app.common.auth`; public account serialization in `teacher_app.auth.service` | `app.py` exposes thin `normalize_role`, `has_permission`, `_current_user`, and `require_roles` seams; `rbac_681.py` adapts legacy endpoints and group scoping | **Frozen / converged.** Professional title and responsibility tags are presentation-only and never authorization input. |
| Exam attempt grading and integrity | `teacher_app.exams.grading`, `repository`, `service`, `routes` | `exam_integrity.py` only re-exports canonical helpers and mounts the unchanged legacy URLs | **Frozen / converged.** New exam attempt logic belongs in `teacher_app.exams`. |
| PGY atomic transitions and signing | `teacher_app.pgy.service`, `repository`, `workflow`, `signing` | `pgy_atomic.py` delegates the six state transitions; `pgy_signing_66.py` is a compatibility overlay | **Partially converged.** Preserve old contracts and move the remaining read/create/edit controller logic only as a separately tested follow-up. |
| PGY route controller / legacy workflow | target: `teacher_app.pgy.routes` plus the service/repository above | `pgy_workflow.py` still owns registration, metadata, candidate/list/create/edit routes, and part of the legacy schema seam | **Deferred debt.** It contains substantial unique production logic; do not force-move it during this phase. |
| Worker queue and local-worker HTTP adapter | `free_worker_67.py` plus `material_worker.py`; queue/storage helpers remain in `app.py` | `pgy_app.py` registers `register_free_worker`; `health_65.py` reports status | **Deferred debt.** The adapter has unique queue/upload protocol logic. Keep local tokens server-side and do not introduce a second worker. |
| Smart learning / material progress | `smart_learning_67.py` | `pgy_app.py` registration only; material storage remains in `app.py` | **Deferred debt.** Unique reader, media-coverage, and preview behavior remains here. |
| Question Bank 2.0 | `question_bank_68.py` | `rbac_681.py` scopes legacy and Bank 2.0 endpoints | **Deferred debt.** Unique blueprint/analytics logic; no duplicate module exists yet. |
| External interactive media | `external_media_68.py` | `pgy_app.py` registration and RBAC adapter | **Deferred debt.** Unique URL validation and material adapter; keep server-side validation. |
| Admin elevation | `admin_elevation_68.py` | `sensitive_elevation_69.py` consumes its exported guard | **Frozen as one adapter pair.** New sensitive operations extend `SENSITIVE_RULES`, never duplicate elevation storage/session checks. |
| Legacy materials, courses, assessments, storage | future `teacher_app.materials` / related services | predominantly `app.py` | **Deferred debt.** These remain substantial unique logic; this phase does not rewrite them. |

## Root freeze policy

1. `pgy_app.py` is composition only.  It may register explicitly named compatibility adapters, but not add business rules.
2. `app.py` auth/RBAC seams must delegate to `teacher_app`; preserved `_legacy_*` routines are compatibility fixtures and must not be used by live `/api/auth/*` routes.
3. `exam_integrity.py` remains a thin adapter.  New exam-attempt behavior goes in `teacher_app.exams`.
4. The PGY atomic action adapter must call `teacher_app.pgy.service`.  Until the deferred controller inventory is addressed, do not copy additional PGY rules into `pgy_workflow.py`.
5. Do not use `professional_title` or `responsibility_tags` in roles, permissions, scope, elevation, or query filters.
6. Student management access, auditor immutability, group scope, cross-group education-admin access, system-admin limits on clinical signing, elevation, and worker-secret boundaries remain governed by their existing security tests.

`tests/test_root_mirror_policy.py` is the CI enforcement point.  It verifies the live auth route delegates, the canonical RBAC seams, the thin exam adapter, PGY atomic-service delegation, the unchanged production entrypoint, and that this matrix remains present.  Any new modularized-domain root implementation requires an explicit ownership decision and a policy-test update in the same review.

## Follow-up sequence

1. Extract the remaining PGY controller reads/create/edit behind `teacher_app.pgy` while preserving every legacy URL and response shape.
2. Inventory `app.py` materials/course/assessment ownership before extracting one low-risk adapter at a time.
3. Only after each domain has no unique legacy logic should `app.py` shrink from compatibility host to a true shim.
