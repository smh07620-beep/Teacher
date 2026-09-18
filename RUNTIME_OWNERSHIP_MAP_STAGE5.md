# Runtime Ownership Map — Stage 5

Branch target: `feature/teacher-content-authoring-studio-72`

This map records *runtime ownership*, not just file placement. A module is only considered converged when its canonical domain owns data access/business behavior and the legacy host is limited to URL/format compatibility.

## Production entrypoint

`pgy_app.py` still imports `app.py` as `legacy_app`. Therefore the application factory convergence is **not complete**. Do not switch to `teacher_app.create_app()` until the remaining runtime owners below have been migrated and regression-tested.

## Register modules in `pgy_app.py`

### A. Startup / cross-cutting infrastructure — keep as explicit registration for now

These are not ordinary domain implementations and should not be removed merely to shorten the register list:

- `register_schema_migrations` — startup schema migration runner.
- `register_health` — health/deployment diagnostics.
- `register_production_hardening` — same-origin/rate-limit/request hardening.
- `register_upload_hardening` — upload validation/hardening.
- `register_ai_privacy` — AI/privacy guardrail.
- `register_exam_integrity` — exam security/integrity overlay.
- `register_admin_elevation` — privileged-session elevation.
- `register_sensitive_elevation_69` — short-lived elevation for destructive/sensitive operations.
- `register_rbac_681` — canonical session/capability RBAC bridge.
- `register_pgy_frontend` — temporary production asset injection while the HTML shell is still legacy-owned.

### B. Canonical Teacher modules — already valid owners

- `register_training_audience_71` — explicit training-track audience state; does not grant RBAC.
- `register_training_command_center` — read-only aggregation surface over canonical domains.

### C. Compatibility adapters — keep only while the original URL/shell contract exists

- `register_pgy_workflow` — surviving thin PGY legacy URL/JSON adapter over `teacher_app.pgy`; no independent schema/business ownership.
- `register_legacy_office_69` — compatibility route; must stay thin and defer authorization to canonical RBAC.
- `register_atlas_70` — Atlas HTTP compatibility adapter; CRUD/search/local-image/DOCX import runtime ownership is canonical and the adapter retains only established HTTP/RBAC/config seams.

### D. Runtime domain owners still pending convergence

These modules still own meaningful runtime behavior and must be migrated domain-by-domain before they can disappear from `pgy_app.py`:

- `register_multi_role_66`
- `register_pgy_signing_66`
- `register_backup_restore`
- `register_smart_learning`
- `register_free_worker`
- `register_external_media`
- `register_course_bundle_72`
- `register_course_bundle_followup_73`
- `register_question_bank`

`register_pgy_atomic_workflow` is **retired**. It only replaced six existing PGY mutation endpoints with the same canonical `teacher_app.pgy.service` handlers and had no unique runtime ownership.

Removing any remaining runtime owner by name alone would be cosmetic convergence and risks deleting real behavior.

## Domain status

### Materials — ordinary host dependency removed; storage seam deferred

Completed:

- All runtime `materials` SQL is owned by `teacher_app.materials.repository`.
- Repository reads/writes use `teacher_app.common.db` pooled connection/transaction seams.
- `app.py` material SQL was removed.
- Course/assessment/external-media material relation writes join explicit transactions.
- Group/area normalization is canonical in `teacher_app.common.scope`.
- Built-in catalog loading/basic labels are canonical in `teacher_app.materials.catalog`.
- Course/category validation reads use `teacher_app.courses.repository` and `teacher_app.assessments.repository`.
- `teacher_app.materials.repository` no longer consults the legacy `base` object; its legacy first argument is compatibility-only.

Remaining legacy dependency:

- physical provider deletion (`mega_destroy`, GDrive/R2/OCI delete);
- legacy local upload/cache filesystem paths used during deletion.

Those are storage-provider responsibilities and should move only when one canonical `teacher_app.storage` seam is established.

### Courses — next data-access owner to converge

`teacher_app.courses.service` still calls legacy host methods such as `base.list_courses`, `base.get_course`, `base._db_conn`, `base.normalize_area` and `base.normalize_group`. `teacher_app.courses.repository` now exists as the canonical read seam, but create/update and teaching-plan paths are not fully migrated yet. The target is:

`legacy URL -> thin adapter -> teacher_app.courses.service -> teacher_app.courses.repository -> teacher_app.common.db`

Material relation SQL already delegates to `teacher_app.materials.repository` and should remain that way.

### Assessments — follow courses

`teacher_app.assessments.repository` now owns the first category read/label seam, but `teacher_app.assessments.service` still depends on `base` for list-with-counts, question reads and several writes. Do not migrate it in the same commit as courses. Move each read/write family to the canonical DB seam separately and preserve the short category-list cache behavior.

### PGY workflow — canonical business owner established; signing overlay pending

Completed:

- PGY schema, repository queries, transitions, validation and audit writes are canonical in `teacher_app.pgy`.
- `pgy_workflow.py` is a compatibility HTTP/JSON adapter only.
- The redundant `pgy_atomic.py` view-function replacement layer is retired.

Remaining:

- `pgy_signing_66.py` still owns unique multi-role and single/dual sign-mode route behavior, candidate/list/get projections and some DB access. Move those rules into `teacher_app.pgy.service/repository/signing` before shrinking the adapter.

### Backup / restore — pending

`backup_restore.py` still owns archive creation, manifest/hash validation and conservative restore orchestration. Security/elevation behavior must remain unchanged while persistence/archive implementation moves to a canonical maintenance package.

### Smart learning — pending

`smart_learning_67.py` still owns reader progress, coverage, preview/indexing integration and API behavior. Converge the state/repository logic before touching the frontend adapter.

### Worker — pending

`free_worker_67.py` and `material_worker.py` still own unique queue/worker protocol behavior. Preserve the existing single-worker protocol and server-side token boundary; do not create a second queue implementation.

### External media — pending

`external_media_68.py` still owns URL normalization/validation and external material creation orchestration. Move validation/persistence into a canonical external-media domain while keeping current public contracts.

### Course bundle — pending

`course_bundle_72.py` and `course_bundle_followup_73.py` own idempotent course/exam creation and material follow-up workflow state. Converge together only at the service/repository boundary while preserving the two-stage HTTP contract and idempotency migrations.

### Atlas — runtime ownership canonical; HTTP compatibility only

Completed:

- `teacher_app.atlas.repository` owns Atlas row projection plus `atlas_items` reads and writes.
- `teacher_app.atlas.service` owns group scope, read/manage visibility, draft/published filtering and CRUD validation.
- `teacher_app.atlas.search` owns `/api/teaching-resource-search` aggregation across readable materials and Atlas records.
- `teacher_app.learning.repository` remains the sole `material_text_index` SQL owner; Atlas search reuses `get_material_text_rows()` instead of creating a parallel search-index repository.
- `teacher_app.atlas.image_store` owns local `atlas_images` directory creation, extension/content validation, image persistence, thumbnail generation and safe request-name projection.
- `teacher_app.atlas.importer` owns canonical-first material lookup, DOCX source-path resolution, preview parsing, embedded-image selection, metadata merge, image persistence delegation and draft Atlas item creation.
- Manual Atlas image upload and DOCX-selected embedded images both use the same canonical image writer; `atlas_70.py` no longer imports Pillow/BytesIO or creates thumbnails itself.
- `atlas_70.py` contains no Atlas-table CRUD SQL, no `material_text_index` SQL, no ZIP parser and no DOCX item-creation implementation; routes delegate to canonical Atlas modules.
- A narrow `legacy_material_getter` fallback remains only for isolated legacy-host/test fixtures after canonical material lookup returns no record. It owns no SQL, path rules or import behavior.

Source cleanup note:

- `smart_learning_67.py` still contains the old `preview_docx_atlas` helper as dead compatibility source, but Atlas runtime no longer imports or calls it. Remove or convert it to a re-export when the Smart Learning domain is converged, rather than reopening Atlas ownership.

### Question Bank — CRUD/review canonical; blueprint/analytics pending

Completed:

- `teacher_app.assessments.repository` owns Bank 2.0 `quiz_questions` list/get/duplicate-candidate/insert/update/delete/review SQL.
- `teacher_app.assessments.question_bank` owns Bank metadata validation, payload projection, duplicate detection, draft creation, editing, deletion and review transitions.
- `question_bank_68.py` keeps the existing `/api/question-bank/*` HTTP/RBAC surface but delegates CRUD/review behavior to the canonical assessment modules.
- Structural regression coverage prevents `quiz_questions` CRUD/review SQL from returning to the root adapter.

Remaining:

- exam blueprint persistence and exact-quota selection (`exam_blueprints`, `_draw`);
- immutable blueprint snapshot publication (`exam_blueprint_snapshots`);
- item analytics aggregation (`question_attempt_analytics`).

Those remaining behaviors should migrate into assessment-owned canonical modules without creating a second assessment publication owner.

## Storage / MEGA ownership

The active legacy provider engine remains in `app.py`. Teacher's default MEGA root is `smh-teaching-materials`; each uploaded material is stored below `<MEGA_ROOT_FOLDER>/<material_id>/`.

Provider credentials, MEGAcmd process/session handling, cloud upload/download and destructive remote delete are still storage-provider responsibilities and should move to a canonical `teacher_app.storage` provider layer before the final app-factory cutover.

Do **not** add a second MEGA client or second connection/session implementation while migrating this layer.

## Ordered convergence plan

1. Finish PGY by moving unique multi-role/sign-mode behavior out of `pgy_signing_66.py` into `teacher_app.pgy`.
2. Move backup/restore ownership into a canonical maintenance domain.
3. Move smart-learning state/data ownership into a canonical domain; retire its dead Atlas preview helper during that cleanup.
4. Move worker queue/protocol ownership without creating a second worker implementation.
5. Move external-media validation/persistence ownership.
6. Move course-bundle and follow-up workflow ownership while preserving idempotency.
7. Atlas runtime convergence is complete; keep `register_atlas_70` only as the established HTTP compatibility adapter until app-factory cutover.
8. Finish Question Bank by moving blueprint/snapshot and analytics ownership into `teacher_app.assessments` without duplicating assessment publication logic.
9. Continue course/assessment repository migration and provider/storage extraction in bounded slices.
10. Only after the runtime ownership map has no domain implementation in `app.py`, replace `pgy_app.py` with `app = create_app()`.

## Deletion rule

For every migration:

1. establish canonical owner;
2. redirect the existing route/consumer to it;
3. run the full release gate;
4. delete the previous implementation;
5. add a structural regression guard preventing the duplicate owner from returning.
