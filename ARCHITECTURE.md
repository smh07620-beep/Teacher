# Teacher current architecture

This document is the canonical architecture and ownership contract for the current Teacher application. Historical release architecture for 6.5, 6.6, and 6.7 is preserved in `docs/archive/ARCHITECTURE_HISTORY.md`.

Formal release SemVer is `6.8.1`. Internal UI/convergence naming currently reaches `7.9 / RC79`; these 7.x generation labels are engineering milestones and do not change the formal release version unless `VERSION` is intentionally updated under the release contract.

## Production composition

- Production entrypoint remains `pgy_app:app`; `pgy_app.py` is a thin WSGI shim whose only production composition action is `app = teacher_app.create_app()`.
- Production composition is owned by `teacher_app.factory.create_app()`. The factory builds a fresh Flask app, runs bootstrap/migrations, registers canonical blueprints and domain route packages, then installs common error handling.
- Root `app.py` is an import-compatibility alias to `teacher_app.legacy_host` for historical callers and isolated tests. Production startup through `pgy_app:app` does not import root `app.py` or `teacher_app.legacy_host`, and root `app.py` owns no production composition, database, provider, or business rules.
- SQLite/PostgreSQL compatibility is preserved. Canonical database access uses `teacher_app.common.db` connection and transaction helpers.
- Render runs the Web Service only. Durable material conversion is performed by the separately operated local/hospital worker over the protected worker API.

## Security and identity invariants

Canonical roles are `student`, `clinical_teacher`, `group_leader`, `education_admin`, `system_admin`, and `auditor`. Legacy `learner`, `teacher`, and `manager` values are normalized at the authorization boundary for compatibility.

Authorization remains server-side and scope-aware. `professional_title` and `responsibility_tags` are display metadata and must never become authorization inputs. `system_admin` and `education_admin` do not gain clinical signing authority unless the account actually carries the required clinical role. Signed/finalized clinical records must use the explicit correction workflow rather than silent overwrite.

Exam grading is server-authoritative. Learner payloads before submission do not receive answer keys, explanations, or protected review-source data, and duplicate/concurrent submission is guarded by the canonical exam attempt workflow.

## Canonical backend ownership

| Domain | Canonical owner | Compatibility surface / current status |
| --- | --- | --- |
| Auth and session lifecycle | `teacher_app.auth.service`, `teacher_app.auth.repository`, `teacher_app.auth.routes` | Production routes are registered by `teacher_app.factory`; `teacher_app.legacy_host` preserves isolated compatibility delegates only. **Frozen / converged.** |
| RBAC, canonical roles and scope | `teacher_app.common.auth`, `teacher_app.common.scope` | Legacy role aliases and old endpoint shapes may remain, but permission decisions stay canonical. **Frozen / converged.** |
| Exam attempts and grading | `teacher_app.exams` | `exam_integrity.py` preserves legacy registration/exports only. **Frozen / converged.** |
| PGY workflow and signing | `teacher_app.pgy.service`, `repository`, `workflow`, `signing`, `signing_facade` | Root PGY modules keep HTTP/schema-registration compatibility only. **Converged runtime dispatch.** |
| Materials catalog and metadata | `teacher_app.materials.service`, `repository`, `catalog` | Legacy `/api/slides*` routes delegate to canonical services. **Converged read/data ownership.** |
| Courses and teaching plans | `teacher_app.courses.service` plus repositories | Canonical repositories own course SQL and the service owns course workflow rules; historical URLs remain stable without restoring root data-access ownership. **Converged data/rule ownership.** |
| Course Wizard bundle/follow-up | `teacher_app.courses.bundle`, `teacher_app.courses.bundle_routes`, `teacher_app.courses.bundle_followup`, `teacher_app.courses.bundle_followup_routes` | Root `course_bundle_72.py` / `course_bundle_followup_73.py` are compatibility aliases only; 0072/0073 DDL is owned by `teacher_app.maintenance.migrations`. |
| Assessment configuration/review/publication | `teacher_app.assessments.service` plus repositories | Existing category/question URLs retain compatibility adapters; business rules stay canonical. |
| Storage providers and deletion | `teacher_app.storage.providers`, `teacher_app.storage.service`, `teacher_app.storage.runtime` | Provider credentials/client construction and process-local provider state are canonical. Strict explicit deletion and best-effort replacement/orphan cleanup use canonical adapters. Remaining upload/read rewires may still pass through compatibility callers until migrated. |
| Worker queue and protocol state | `teacher_app.worker.repository`, `teacher_app.worker.protocol`, `teacher_app.worker.routes` | Canonical persistence owns `material_jobs`, upload-session state, heartbeat reads, atomic claim/CAS transitions and pure protocol validation. Canonical HTTP registration owns claim/heartbeat/terminal/direct-upload routes. The executable worker remains `material_worker.py`; `free_worker_67.py` is import compatibility only. |
| Smart learning | `teacher_app.learning` | `smart_learning_67.py` is a compatibility registration surface for remaining live reader/media behavior. |
| Atlas | `teacher_app.atlas.service`, `teacher_app.atlas.repository`, `teacher_app.atlas.routes` | Root `atlas_70.py` is a compatibility alias only; canonical routes own established URL/transport behavior. |
| External interactive media | `teacher_app.materials.external_media`, `teacher_app.materials.external_media_routes` | Root `external_media_68.py` is a compatibility alias only; validation/persistence and HTTP registration are canonical. |
| Admin elevation | `teacher_app.auth.elevation` | Root `admin_elevation_68.py` / `sensitive_elevation_69.py` preserve historical registration/export names only; canonical elevation state and rules stay in-package. |

## Storage and material-processing architecture

Large material uploads use Browser → R2 multipart direct upload for shared staging. The Web validates declared metadata and completion state before creating runnable work. The trusted local/hospital worker claims jobs over HTTPS, validates the downloaded object again, performs conversion, publishes final content using the configured provider policy, and reports completion through the worker API.

`teacher_app.storage.providers` owns live provider configuration, SDK/client construction and the process-local MEGA session cache. `teacher_app.storage.service` owns backend selection and provider-neutral strict/best-effort deletion semantics. `teacher_app.storage.runtime.build_delete_adapters()` wires existing live provider callbacks into the canonical deletion interface without creating a second client or session.

Explicit admin deletion is strict: provider cleanup failures must surface through the established HTTP error contract. Replacement/orphan cleanup is best-effort so a successful replacement is not converted into a failed user operation solely because stale-object cleanup failed.

`teacher_app.worker.repository` owns Web-side worker persistence and transaction boundaries; it must not own DDL, HTTP routes, executor behavior or storage adapters. `teacher_app.worker.protocol` owns pure bearer-token validation, retry planning, multipart completion validation and heartbeat metadata rules. `teacher_app.worker.routes` owns the Web HTTP adapter for the same protocol and queue. The system must keep one local-worker protocol and one `material_jobs` queue rather than introducing a second executor or queue.

## Frontend ownership freeze

- `static/system-admin.js` is a legacy compatibility bundle. It must not receive new product logic.
- `static/course-wizard-681.js` is the canonical Course Wizard UI/state owner.
- `static/admin-compat-facade.js`, `static/assessment-681.js`, `static/question-authoring-ux-71.js`, and `static/runtime-escape-guard-7111.js` are removed. Current HTML and runtime manifests call canonical owners directly.
- `static/assessment-advanced-74.js` is the sole owner for blueprint snapshots and item analytics; normal exam/question management remains with the canonical admin modules.
- `static/shared-core.js` owns the global `escapeHtml` compatibility export until remaining callers move to `AppCore.escapeHtml`.
- Blueprint snapshot/item analytics UI belongs to `static/assessment-advanced-74.js`; it must not re-own question CRUD or AI authoring.
- `getAdminKey()` remains a compatibility header seam only; session RBAC is the authorization boundary.

### Canonical frontend owners

| Responsibility | Canonical owner |
| --- | --- |
| Course Wizard UI/state | `static/course-wizard-681.js` |
| Material background transport | `static/material-upload-client.js` |
| Workspace routing | `static/admin-workspace.js` |
| Result data/workspace/export | `static/admin-results-data.js`, `static/admin-results-workspace.js`, `static/admin-results-export.js` |
| Course/material management | `static/admin-course-material.js`, `static/admin-materials.js` |
| Question bank/editor/actions/panel | `static/admin-question-bank.js`, `static/admin-question-editor-ui.js`, `static/admin-question-actions.js`, `static/admin-question-panel.js` |
| AI-assisted question generation | `static/admin-ai-questions.js` |
| Exam settings/review/publish | `static/admin-exam-settings.js` |
| Assessment blueprint snapshots / item analytics | `static/assessment-advanced-74.js` |
| People / announcements / system status | `static/admin-people.js`, `static/admin-announcements.js`, `static/admin-system.js` |
| PGY clinical assessment form / submission / learner history | `static/system-assessment.js` |
| PGY assessment administration / templates / admin record list | `static/admin-pgy-assessments.js` |
| Document templates | `static/admin-doc-templates.js` |
| External media | `static/admin-external-media.js` |
| Learner exam/result compatibility | `static/learner-exam-controls.js`, `static/learner-result-chart.js` |

The final frontend target is one normal user-facing runtime owner per responsibility, with compatibility files reduced to thin routing/bootstrap seams.

## Root freeze policy

1. `pgy_app.py` remains the thin production WSGI entrypoint and obtains the Flask app from `teacher_app.create_app()`; production composition belongs in `teacher_app.factory`.
2. `app.py` remains a compatibility alias only; production startup must not depend on it or regain database, provider or business-rule ownership.
3. `exam_integrity.py` remains a thin adapter; new exam-attempt behavior belongs in `teacher_app.exams`.
4. PGY rules, persistence, scope and signing dispatch belong in `teacher_app.pgy`; root PGY modules preserve HTTP/registration compatibility only.
5. Materials, course and assessment business/data rules belong in their canonical services/repositories. Root route bodies must not regain independent SQL, provider branching or validation policy.
6. Course-bundle workflow state stays in `teacher_app.courses.*`; release migration ownership stays in `teacher_app.maintenance.migrations` with pre-migration coordination in `teacher_app.maintenance.bootstrap`.
7. Atlas CRUD/scope belongs in `teacher_app.atlas`; remaining transport/parsing seams may stay in the adapter until separately migrated.
8. External-media URL policy and persistence belong in `teacher_app.materials.external_media`.
9. Storage provider credentials/client construction belong in `teacher_app.storage`. Canonical consumers should use the shared provider/runtime seams rather than constructing parallel clients or sessions.
10. Worker queue/upload-session persistence, pure protocol rules and Worker HTTP registration belong in `teacher_app.worker`. The existing executable worker remains the single worker loop.
11. `professional_title` and `responsibility_tags` must not be used for authorization, scope or elevation.
12. Student isolation, auditor immutability, group scope, cross-group education-admin access, system-admin clinical-signing limits, elevation and worker-token boundaries remain protected by server-side tests.

### Retained root compatibility inventory

The following root modules are intentionally retained compatibility seams. They are not production composition owners, and new business/data/provider logic must not be added to them:

- Import/module aliases: `app.py`, `schema_migrations.py`, `pgy_frontend.py`, `external_media_68.py`, `question_bank_68.py`, `course_bundle_72.py`, `course_bundle_followup_73.py`, `atlas_70.py`, `backup_restore.py`, `rbac_681.py`, `upload_hardening.py`, `legacy_office_69.py`.
- Thin registration/export adapters: `health_65.py`, `free_worker_67.py`, `exam_integrity.py`, `pgy_workflow.py`, `pgy_signing_66.py`, `smart_learning_67.py`, `multi_role_66.py`, `admin_elevation_68.py`, `sensitive_elevation_69.py`, `production_hardening.py`, `ai_privacy.py`.
- Historical/internal root helper: `media_processing_67.py` contains only worker capability metadata helpers. It has no production registration or executor caller; `material_worker.py` remains the sole worker executable.
- Package-level historical helpers under `teacher_app.compatibility`: `__init__.py` is namespace documentation, `legacy_app.py` preserves the old `load_legacy_app()` helper by returning canonical `pgy_app.app`, and `legacy_routes.py` documents retired/root route compatibility. None is imported by `teacher_app.factory` or owns production routes/business logic.
- `pgy_app.py` is not a compatibility adapter: it is the intentionally thin WSGI entrypoint. `material_worker.py` is likewise not a compatibility adapter: it is the single local/hospital worker executable.

These files exist for established imports, old extension/test fixtures, or stable registration/export names. Production `teacher_app.factory.create_app()` imports canonical package owners directly and does not compose through the root adapters.

## Deployment and operations

Render runs `pgy_app:app` and probes `/health`. Production requires a valid PostgreSQL/Supabase `DATABASE_URL`, session secrets and the credentials for enabled storage/AI providers. Secrets are environment configuration and must not be committed to the repository.

The Web Service does not supervise `material_worker.py`. The local/hospital worker uses `MATERIAL_WORKER_TOKEN`, does not require a learner session, and does not receive production database credentials. Worker availability intentionally does not determine `/health` success.

## Current convergence boundary

The production factory cutover is complete: `pgy_app:app` resolves through `teacher_app.create_app()` and production composition no longer depends on root `app.py` / `teacher_app.legacy_host`. Remaining convergence work is compatibility deletion and narrower owner-seam cleanup inside individual domains. Runtime-owner adapters that remain in assessment/worker/material-job packages (`runtime_from_owner(...)` / `from_compat_owner(...)`) are isolated compatibility paths; production factory wiring supplies explicit canonical runtimes. Compatibility code should be deleted only after its remaining isolated callers move and release checks cover the replacement.

Historical release architecture and migration notes are retained in `docs/archive/ARCHITECTURE_HISTORY.md` for traceability and must not be treated as the current ownership contract.
