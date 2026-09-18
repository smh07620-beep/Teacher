# Root mirror cleanup — ownership inventory and freeze

## Purpose and boundary

This document records the root-module ownership cleanup. Production remains **`pgy_app:app`**. `app.py` is not deleted and remains the compatibility host while domains are progressively moved behind canonical modules.

The rule is simple: when a domain has a canonical `teacher_app/` owner, new business rules, authorization decisions, persistence behavior, and HTTP semantics belong there. A root file may keep a route name, legacy response shape, registration call, or narrowly scoped adapter only. It must not become a second implementation.

This cleanup makes no database migration, Render change, version change, or production-entrypoint change.

## Completed stale frontend mirror removal

`static/` is the sole canonical web-asset directory: the Flask application is
configured with `STATIC_DIR = BASE_DIR / "static"` and every public page route
uses that directory. The former root copies of the following same-named
assets have therefore been removed. They were stale mirrors, not fallback
assets or production entrypoints:

- HTML: `index.html`, `area-internal.html`, `area-pgy.html`, `login.html`, and
  `system.html`
- JavaScript: `login.js`, `portal-v56.js`, `shared-core.js`, `system-admin.js`,
  `system-assessment.js`, `system-bootstrap.js`, `system-core.js`,
  `system-exam.js`, `system-learner.js`, and `teaching.js`
- CSS: `admin.css`, `design-tokens.css`, `learner.css`, `phase3.css`,
  `portal-v56.css`, `portal-v571.css`, `portal.css`, `teaching.css`, `v561.css`,
  `v573.css`, `v574.css`, `v575.css`, and `v580.css`

Do not recreate a root copy of a file that is served from `static/`. A new
root/static same-name pair requires an explicit compatibility decision and a
corresponding policy-test update. Deferred Python modules in the ownership
matrix remain intentionally untouched while they still have unique production
behavior.

## Canonical ownership matrix

| Domain | Canonical owner | Root compatibility surface | Status / remaining debt |
| --- | --- | --- | --- |
| Auth and session lifecycle | `teacher_app.auth.service`, `repository`, `routes` | `app.py` exposes only thin live delegates needed by legacy route names | **Frozen / converged.** Pre-extraction `_legacy_*` auth implementations have been retired; keep old URLs and JSON contracts through canonical delegates only. |
| RBAC, canonical roles, permissions | `teacher_app.common.auth`; public account serialization in `teacher_app.auth.service` | `app.py` exposes thin `normalize_role`, `has_permission`, `_current_user`, and `require_roles` seams; `rbac_681.py` adapts legacy endpoints and group scoping | **Frozen / converged.** Professional title and responsibility tags are presentation-only and never authorization input. |
| Exam attempt grading and integrity | `teacher_app.exams.grading`, `repository`, `service`, `routes` | `exam_integrity.py` only re-exports canonical helpers and mounts the unchanged legacy URLs | **Frozen / converged.** New exam attempt logic belongs in `teacher_app.exams`. |
| PGY workflow, atomic transitions and signing | `teacher_app.pgy.service`, `repository`, `workflow`, `signing`, `signing_facade` | `pgy_workflow.py` preserves legacy PGY URLs/JSON; `pgy_signing_66.py` preserves 6.6 URL replacement, schema startup and response compatibility | **Converged runtime dispatch.** Reads, create/edit rules, atomic transitions, audit writes, multi-role scope and legacy/new sign-mode dispatch belong to `teacher_app.pgy`. Root signing code no longer decides which workflow executes. |
| Materials catalog and metadata controller | `teacher_app.materials.service`, `repository`, `catalog`; shared scope in `teacher_app.common.scope` | Existing `/api/slides*` endpoint names remain in `app.py` as thin canonical delegates; provider deletion still calls narrow legacy storage seams | **Converged read/data ownership.** Repository and normal catalog/update validation no longer consult the legacy host. Provider delete/filesystem cleanup remains deferred until storage ownership moves. |
| Courses and teaching-plan controller | `teacher_app.courses.service` plus incremental `teacher_app.courses.repository` | Existing `/api/courses*` URL rules remain in `app.py` as thin canonical delegates; no runtime view-function replacement remains in `pgy_app.py` | **Converged controller, data-access migration pending.** Course CRUD/plan rules are canonical, but several reads/writes still depend on legacy host seams. |
| Course Wizard bundle creation and follow-ups | `teacher_app.courses.bundle`, `teacher_app.courses.bundle_followup`; 0072/0073 schema in `schema_migrations.py` | `course_bundle_72.py` keeps `/api/course-bundles`, capability gates and response projection; `course_bundle_followup_73.py` keeps the wrapper around the established upload/link handlers | **Converged runtime + migration ownership.** Atomic course/draft-exam creation, workflow hashing/idempotency, follow-up scope checks and claim/release/complete persistence are canonical. Root adapters retain HTTP/RBAC/handler-wrapping compatibility only and no longer register or contain 0072/0073 DDL. |
| Assessment configuration/review/publication | `teacher_app.assessments.service` plus incremental `teacher_app.assessments.repository` | Existing `/api/quiz-categories*` URL rules remain in `app.py` as thin canonical delegates; Question Bank/RBAC adapters may still wrap those handlers | **Converged controller, data-access migration pending.** Review/publication rules are canonical while some category/question reads and writes still depend on legacy host seams. |
| Material storage/conversion providers | legacy storage helpers in `app.py` plus worker adapters | `teacher_app.materials` calls narrow seams such as `gdrive_delete_material`, `mega_destroy`, `r2_delete_prefix` and `oci_delete_prefix` only for physical provider cleanup | **Deferred storage debt.** Credentials, provider SDK clients, upload/preview conversion and worker protocol are intentionally not duplicated in canonical modules yet. |
| Worker queue and local-worker HTTP adapter | `free_worker_67.py` plus `material_worker.py`; queue/storage helpers remain in `app.py` | `pgy_app.py` registers `register_free_worker`; `health_65.py` reports status | **Deferred debt.** The adapter has unique queue/upload protocol logic. Keep local tokens server-side and do not introduce a second worker. |
| Smart learning / material progress | `teacher_app.learning` plus `smart_learning_67.py` compatibility registration | `pgy_app.py` registration only; material storage remains in `app.py` | **Converging.** Smart-learning persistence/SQL is canonical; remaining reader/media compatibility behavior stays behind the existing adapter until its callers are retired. |
| Atlas teaching resources | `teacher_app.atlas.service`, `teacher_app.atlas.repository`; 0070 schema in `schema_migrations.py` | `atlas_70.py` keeps established URLs, local image/DOCX transport compatibility and the material-text search adapter | **CRUD/scope converged.** Atlas row projection, visibility/scope policy, filtering and all runtime `atlas_items` CRUD SQL are canonical. Remaining debt is local image transport, DOCX source/file parsing and `material_text_index` teaching-resource search. |
| Question Bank 2.0 | `question_bank_68.py` | `rbac_681.py` scopes legacy and Bank 2.0 endpoints | **Deferred compatibility overlay.** Do not duplicate category/review/publication rules back into this adapter. |
| External interactive media | `teacher_app.materials.external_media` | `external_media_68.py` preserves routes, permission gates, legacy validator export and response projection; `pgy_app.py` keeps registration | **Converged runtime owner.** URL safety validation, course/assessment scope checks, external-media SQL and atomic material creation are canonical. The root adapter no longer owns persistence or URL policy. |
| Admin elevation | `admin_elevation_68.py` | `sensitive_elevation_69.py` consumes its exported guard | **Frozen as one adapter pair.** New sensitive operations extend `SENSITIVE_RULES`, never duplicate elevation storage/session checks. |

## Root freeze policy

1. `pgy_app.py` is composition only. It may register compatibility modules that still own unique runtime behavior, but it must not reintroduce `register_legacy_material_routes`, `register_legacy_course_routes`, `register_legacy_assessment_routes`, `register_pgy_atomic_workflow`, or other redundant view-function replacement layers.
2. `app.py` auth/RBAC seams must delegate to `teacher_app`; duplicate pre-extraction `_legacy_*` auth implementations must not return to production source.
3. `exam_integrity.py` remains a thin adapter. New exam-attempt behavior goes in `teacher_app.exams`.
4. `pgy_workflow.py` must remain a thin HTTP compatibility adapter: no independent PGY schema SQL, assignment query implementation, create/edit business rules, transition rules, or audit persistence may return to it. `pgy_signing_66.py` must remain an HTTP/schema-registration compatibility surface; multi-role scope and legacy/new signing dispatch belong to `teacher_app.pgy.signing_facade`, while signing transactions belong to `teacher_app.pgy.signing`. The retired `pgy_atomic.py` must not return.
5. Materials catalog/metadata, course/teaching-plan, and assessment category/review/publication rules belong to their `teacher_app` services/repositories. The corresponding `app.py` route bodies are thin canonical delegates only and must not regain SQL, provider branching, validation policy or independent business rules.
6. Course Wizard bundle creation and retry state belong to `teacher_app.courses.bundle` and `teacher_app.courses.bundle_followup`; 0072/0073 DDL and registration belong only to `schema_migrations.py`. `course_bundle_72.py` must not regain runtime course/exam/idempotency SQL, request hashing or schema registration. `course_bundle_followup_73.py` may wrap the established upload/link handlers, but must not regain workflow-query SQL, scope policy, request hashing, follow-up claim/completion persistence or schema registration.
7. Atlas row projection, visibility/scope rules and `atlas_items` CRUD belong to `teacher_app.atlas`. `atlas_70.py` may keep the existing local image/DOCX transport and material-text search compatibility until those seams move, but it must not regain Atlas-table CRUD SQL or duplicate scope policy.
8. External-media URL validation, metadata SQL and atomic external material creation belong to `teacher_app.materials.external_media`. `external_media_68.py` may keep legacy routes, permission gates and response-shape compatibility, but must not regain those implementations.
9. Provider credentials, cloud SDK setup, upload/conversion engines and worker protocol remain outside the current extraction. Canonical material code may call narrow compatibility seams but must not import or duplicate credentials.
10. Do not use `professional_title` or `responsibility_tags` in roles, permissions, scope, elevation, or query filters.
11. Student management access, auditor immutability, group scope, cross-group education-admin access, system-admin limits on clinical signing, elevation, and worker-secret boundaries remain governed by their existing security tests.

`tests/test_root_mirror_policy.py`, `tests/test_stage51_domain_ownership.py`, `tests/test_pgy_signing_convergence_stage5.py`, `tests/test_external_media_convergence.py`, `tests/test_course_wizard_idempotent_bundle_72.py`, `tests/test_course_bundle_followup_73.py`, `tests/test_course_bundle_migration_ownership.py`, and `tests/test_atlas_convergence_stage5.py` are CI enforcement points. They verify live canonical ownership, compatibility composition order, the unchanged production entrypoint, and that storage/provider implementation has not been accidentally duplicated in canonical domain services.

## Backend convergence stage 1

- The temporary `assessment_performance_712.py` patch module is retired.
- PostgreSQL pooling is owned by `teacher_app.common.db`; the legacy `app._db_conn()` name is now only a thin delegate to that canonical seam.
- Request-scoped authenticated-user caching is owned by `teacher_app.auth.service.current_user()` and is explicitly request-local, never process/global cache state.
- Assessment list indexes are registered in `schema_migrations.py` instead of by importing a performance patch module.
- Materials, courses, and assessment-category legacy URL rules delegate directly from `app.py` to canonical services. Their former `app.view_functions.update(...)` replacement adapters have been removed from runtime composition.

## Backend convergence stage 2 — storage/material hot path

- `storage_pagination_hardening.py` is retired. Bounded S3-compatible pagination, usage calculation and prefix deletion now live in `teacher_app.materials.storage` and are called directly by the R2/OCI compatibility seams.
- `pgy_app.py` no longer monkey-patches storage functions during application startup.
- A successful MEGA login/session is trusted for the configured process-local cache window. Normal material reads no longer spawn `mega-whoami` on every cache hit.
- If a real `mega-get` fails, the read path invalidates the cached auth state, refreshes the MEGA session once and retries once. This preserves recovery without a provider probe on every request.
- Material preview files are immutable for a material id. A non-empty local preview cache entry remains valid until size-based eviction or explicit material deletion; the former time-based expiry that periodically forced a synchronous MEGA re-download has been removed.
- Provider health/capacity probes remain operational/admin concerns and must not be introduced into normal material catalog reads.
- Material row projection and all runtime material SELECT/INSERT/UPDATE/DELETE statements now live in `teacher_app.materials.repository`.
- `app.py` keeps only compatibility delegates; it contains no runtime material DML.
- Read-only repository work uses `teacher_app.common.db.read_connection()`, which always checks out from the shared process-local pool and returns/closes the handle at scope exit.
- Repository-owned writes use `teacher_app.common.db.transaction()`. Cross-domain course/assessment/external-media workflows pass the same caller-owned connection into material repository helpers so commit/rollback stays atomic across all affected tables.
- Canonical material, course and assessment services read material data directly through `teacher_app.materials.repository` rather than bouncing through the legacy host.
- Material row projection, group/area normalization, built-in catalog loading and course/category validation now use canonical `teacher_app` modules rather than consulting the legacy `app` object. Physical provider deletion remains the only intentional material-service legacy seam.

## Production runtime validation stage 3

- Render auto-deploy is gated by passing GitHub checks via `autoDeployTrigger: checksPass`; an unverified branch commit must not become the production release.
- `/health` exposes only non-secret deployment identity (`provider`, branch and short commit) so operators can prove which Git commit is actually serving traffic.
- Material/course hot paths emit bounded operational timing logs for `api_list_slides` and `api_courses` without logging user identity or credentials.
- Web MEGA reads use a 120-second total budget while Gunicorn keeps a 180-second request timeout. Long upload/worker operations retain their separate background budgets.
- Cold MEGA preview/read timeouts return a retryable 504 before the Gunicorn worker timeout instead of allowing provider work to outlive the web request budget.
- Same-origin JavaScript and CSS cache keys are rewritten to the deployed Render commit. Browser cache lifetime may remain long, but a new deployment always receives a new asset URL.
- The six exam-container actions (question, image, video, AI, question management and settings) use one delegated runtime path that resolves the current canonical `window.teacherContentStudioExamAction`; inline duplicate handlers are prohibited.
- Exam-action failures return to a visible Studio error state instead of disappearing into a hidden workspace or unhandled promise rejection.

## Backend convergence stage 5 — runtime owner retirement

- `teacher_app.common.scope`, `teacher_app.materials.catalog`, and incremental course/assessment repositories remove ordinary material catalog/update logic from the legacy host dependency chain.
- The historical `pgy_atomic.py` layer is retired. It only replaced six PGY mutation view functions with the same `teacher_app.pgy.service` handlers already registered by `pgy_workflow.py`, so it had no unique runtime ownership.
- `pgy_workflow.py` remains the single legacy PGY URL/JSON adapter while `teacher_app.pgy.service/repository/workflow` remain the canonical business/data owners.
- Multi-role scope, sign-mode configuration, and legacy/new signing dispatch now live in `teacher_app.pgy.signing_facade`; single/dual signature transactions remain in `teacher_app.pgy.signing`.
- `pgy_signing_66.py` no longer captures or calls legacy Flask handlers to decide runtime behavior. It keeps schema startup, route replacement and legacy response compatibility only.
- External-media validation, metadata persistence and external material creation now live in `teacher_app.materials.external_media`. `external_media_68.py` is reduced to HTTP/RBAC compatibility plus the historical material-response projection callback.
- Course Wizard atomic course/draft-exam creation, workflow hashing and request-state persistence live in `teacher_app.courses.bundle`; follow-up workflow lookup, target/scope validation, stable upload/link hashes and claim/release/complete persistence live in `teacher_app.courses.bundle_followup`. 0072/0073 DDL and registration now live only in `schema_migrations.py`; the root bundle modules keep HTTP/handler compatibility and no schema registration.
- Atlas row projection, list/get/create/update/delete persistence, scope/visibility filtering and CRUD validation now live in `teacher_app.atlas.repository` and `teacher_app.atlas.service`. `atlas_70.py` keeps the established URLs plus local image/DOCX and material-text-search compatibility only.

## Follow-up sequence

1. Converge the remaining unique compatibility domains one at a time: worker and Question Bank. Re-check backup/restore and smart learning only for still-live compatibility behavior; do not redo already-canonical persistence work.
2. Converge Atlas material-text search and local image/DOCX transport as separate bounded slices; do not combine those provider/file seams with worker changes.
3. Extract storage/provider ownership one bounded backend at a time; do not combine cloud credentials, upload jobs, conversion and material metadata into one rewrite.
4. Retire remaining root compatibility logic only after the matching canonical domain owns every live caller and release checks cover the old contract.
5. Only after each domain has no unique legacy logic should `app.py` shrink from compatibility host to a true shim and `pgy_app.py` move to `app = create_app()`.
