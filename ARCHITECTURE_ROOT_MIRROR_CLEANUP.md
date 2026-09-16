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
| PGY workflow, atomic transitions and signing | `teacher_app.pgy.service`, `repository`, `workflow`, `signing` | `pgy_workflow.py` is now a thin legacy URL/JSON adapter; `pgy_atomic.py` and `pgy_signing_66.py` remain compatibility overlays | **Frozen / converged controller ownership.** Schema, reads, create/edit rules, transitions and audit writes belong to `teacher_app.pgy`; compatibility modules may only adapt old HTTP/signing contracts. |
| Materials catalog and metadata controller | `teacher_app.materials.service`, `routes` | Existing `/api/slides*` endpoint names remain mounted by `app.py`; `pgy_app.py` replaces their live handlers before RBAC/wrapper registration | **Stage 5.1 converged runtime ownership.** Catalog projection, metadata update and delete orchestration belong to `teacher_app.materials`; provider SDK/credential/storage primitives remain legacy seams for now. |
| Courses and teaching-plan controller | `teacher_app.courses.service`, `routes` | Existing `/api/courses*` URL rules remain compatible while canonical handlers are registered by `pgy_app.py` | **Stage 5.1 converged runtime ownership.** Course CRUD, teaching-plan validation and persistence orchestration belong to `teacher_app.courses`. |
| Assessment configuration/review/publication | `teacher_app.assessments.service`, `routes` | Existing `/api/quiz-categories*` URL rules remain compatible; Question Bank/RBAC adapters may still wrap the canonical handlers | **Stage 5.1 converged runtime ownership.** Category CRUD, review, publication snapshot orchestration and material-link rules belong to `teacher_app.assessments`. |
| Material storage/conversion providers | legacy storage helpers in `app.py` plus worker adapters | `teacher_app.materials` calls narrow `base` seams such as `gdrive_delete_material`, `mega_destroy`, `r2_delete_prefix` and `oci_delete_prefix` | **Deferred storage debt.** Credentials, provider SDK clients, upload/preview conversion and worker protocol are intentionally not moved in Stage 5.1. |
| Worker queue and local-worker HTTP adapter | `free_worker_67.py` plus `material_worker.py`; queue/storage helpers remain in `app.py` | `pgy_app.py` registers `register_free_worker`; `health_65.py` reports status | **Deferred debt.** The adapter has unique queue/upload protocol logic. Keep local tokens server-side and do not introduce a second worker. |
| Smart learning / material progress | `smart_learning_67.py` | `pgy_app.py` registration only; material storage remains in `app.py` | **Deferred debt.** Unique reader, media-coverage, and preview behavior remains here. |
| Question Bank 2.0 | `question_bank_68.py` | `rbac_681.py` scopes legacy and Bank 2.0 endpoints | **Deferred compatibility overlay.** Do not duplicate category/review/publication rules back into this adapter. |
| External interactive media | `external_media_68.py` | `pgy_app.py` registration and RBAC adapter | **Deferred debt.** Unique URL validation and material adapter; keep server-side validation. |
| Admin elevation | `admin_elevation_68.py` | `sensitive_elevation_69.py` consumes its exported guard | **Frozen as one adapter pair.** New sensitive operations extend `SENSITIVE_RULES`, never duplicate elevation storage/session checks. |

## Root freeze policy

1. `pgy_app.py` is composition only. It may register explicitly named compatibility adapters, but not add business rules.
2. `app.py` auth/RBAC seams must delegate to `teacher_app`; duplicate pre-extraction `_legacy_*` auth implementations must not return to production source.
3. `exam_integrity.py` remains a thin adapter. New exam-attempt behavior goes in `teacher_app.exams`.
4. `pgy_workflow.py` must remain a thin HTTP compatibility adapter: no independent PGY schema SQL, assignment query implementation, create/edit business rules, transition rules, or audit persistence may return to it. Compatibility symbols used by `pgy_signing_66.py` must delegate to `teacher_app.pgy`.
5. Materials catalog/metadata, course/teaching-plan, and assessment category/review/publication rules belong to their Stage 5.1 `teacher_app` services. `app.py` may temporarily retain source-level route stubs while URL registration is converged, but those stubs must not become the production runtime owner again.
6. Provider credentials, cloud SDK setup, upload/conversion engines and worker protocol remain outside the Stage 5.1 extraction. Canonical material code may call narrow compatibility seams but must not import or duplicate credentials.
7. Do not use `professional_title` or `responsibility_tags` in roles, permissions, scope, elevation, or query filters.
8. Student management access, auditor immutability, group scope, cross-group education-admin access, system-admin limits on clinical signing, elevation, and worker-secret boundaries remain governed by their existing security tests.

`tests/test_root_mirror_policy.py` and `tests/test_stage51_domain_ownership.py` are CI enforcement points. They verify live canonical ownership, compatibility composition order, the unchanged production entrypoint, and that storage/provider implementation has not been accidentally pulled into the Stage 5.1 domain services.

## Follow-up sequence

1. Replace the now-shadowed materials/course/assessment route bodies in `app.py` with thin compatibility stubs or remove them only when an equivalent URL-registration seam exists.
2. Extract storage/provider ownership one bounded backend at a time; do not combine cloud credentials, upload jobs, conversion and material metadata into one rewrite.
3. Retire remaining root compatibility logic only after the matching canonical domain owns every live caller and release checks cover the old contract.
4. Only after each domain has no unique legacy logic should `app.py` shrink from compatibility host to a true shim.
