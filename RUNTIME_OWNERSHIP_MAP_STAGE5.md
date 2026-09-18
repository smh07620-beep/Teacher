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

- `register_legacy_office_69` — compatibility route; must stay thin and defer authorization to canonical RBAC.

### D. Runtime domain owners still pending convergence

These modules still own meaningful runtime behavior and must be migrated domain-by-domain before they can disappear from `pgy_app.py`:

- `register_pgy_workflow`
- `register_multi_role_66`
- `register_pgy_atomic_workflow`
- `register_pgy_signing_66`
- `register_backup_restore`
- `register_smart_learning`
- `register_free_worker`
- `register_external_media`
- `register_course_bundle_72`
- `register_course_bundle_followup_73`
- `register_atlas_70`
- `register_question_bank`

Removing any of these by name alone would be cosmetic convergence and risks deleting real runtime behavior.

## Domain status

### Materials — data-access convergence complete; host dependency convergence incomplete

Completed:

- All runtime `materials` SQL is owned by `teacher_app.materials.repository`.
- Repository reads/writes use `teacher_app.common.db` pooled connection/transaction seams.
- `app.py` material SQL was removed.
- Course/assessment/external-media material relation writes join explicit transactions.

Remaining legacy dependency:

`teacher_app.materials.service` and `teacher_app.materials.repository` still accept a `base` legacy host for:

- group/area normalization and defaults;
- built-in `slides_meta.json` loading;
- category label projection;
- course/category lookup validation;
- provider deletion orchestration and legacy filesystem paths.

This is the next materials convergence target. Canonical services must not depend on a legacy application object for ordinary domain rules.

### Courses — next data-access owner to converge

`teacher_app.courses.service` still calls legacy host methods such as `base.list_courses`, `base.get_course`, `base._db_conn`, `base.normalize_area` and `base.normalize_group`. It also still contains direct course SQL. The safe target is:

`legacy URL -> thin adapter -> teacher_app.courses.service -> teacher_app.courses.repository -> teacher_app.common.db`

Material relation SQL already delegates to `teacher_app.materials.repository` and should remain that way.

### Assessments — follow courses

`teacher_app.assessments.service` still depends heavily on `base` for category/question reads, normalization and several DB writes. Do not migrate it in the same commit as courses. First create an assessment repository and move category data access behind the canonical DB seam, then remove `base` calls incrementally.

## Storage / MEGA ownership

The active legacy provider engine remains in `app.py`. Teacher's default MEGA root is `smh-teaching-materials`; each uploaded material is stored below `<MEGA_ROOT_FOLDER>/<material_id>/`.

Provider credentials, MEGAcmd process/session handling, cloud upload/download and destructive remote delete are still storage-provider responsibilities and should move to a canonical `teacher_app.storage` provider layer before the final app-factory cutover.

Do **not** add a second MEGA client or second connection/session implementation while migrating this layer.

## Ordered convergence plan

1. Remove materials read/projection dependency on legacy `base` (normalization, built-in catalog, category/course lookup).
2. Introduce `teacher_app.courses.repository` and move course SQL/read ownership out of the legacy host.
3. Introduce `teacher_app.assessments.repository` and migrate assessment/category SQL in small verified groups.
4. Move provider engines (MEGA/GDrive/R2/OCI) behind canonical `teacher_app.storage` interfaces; keep one MEGAcmd session path.
5. Migrate backup/restore, question-bank, external-media, Atlas and PGY workflow owners into their canonical packages.
6. Only after the runtime ownership map has no domain implementation in `app.py`, replace `pgy_app.py` with `app = create_app()`.

## Deletion rule

For every migration:

1. establish canonical owner;
2. redirect the existing route/consumer to it;
3. run the full release gate;
4. delete the previous implementation;
5. add a structural regression guard preventing the duplicate owner from returning.
