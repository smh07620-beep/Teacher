# Teacher 6.6.0 Architecture and Release

Teacher 6.6.0 is an additive release. It keeps the production entrypoint at
`pgy_app:app`, retains the 6.5 database and API contracts, and applies only
non-destructive database changes through `0066-additive-rbac-pgy-signing`.

## Identity, roles, and PGY signing

- `user_accounts.role` remains the primary legacy role. Existing values such as
  `teacher` normalize to `clinical_teacher` without changing the stored legacy
  value.
- `user_accounts.roles_json` persists normalized multi-role membership. The
  0066 migration fills only empty role sets; it never replaces an existing
  multi-role record.
- New PGY assignments use one signer by default. A configured dual assignment
  requires a different account for the second signature.
- Existing assignments get `sign_mode=legacy` and continue through the original
  student submit, clinical teacher sign, group leader countersign, and education
  admin finalization flow.
- Each signature transition and its audit entry run in the same transaction.
  Failed audit writes roll back the transition.

## Learning and administration experience

- Homepage routing uses the current exam identifier and opens pending exams at
  the correct destination.
- Course and material lists use the 6.6 cache/performance paths. Sequential
  material completion unlocks the next material, while a zero-question exam has
  a clear not-ready state.
- Submitted exam reviews can safely reference PPT/PDF pages, audio/video time,
  image/Atlas regions, and section hints. The learner receives no answer key,
  explanation, or review source before submission.
- Backup and restore controls are limited to system settings. Both system
  settings and people management have a single reachable scroll container.

## Migration, health, and backups

- `0066-additive-rbac-pgy-signing` adds `roles_json`, `sign_mode`,
  `first_signature`, and `second_signature` without removing legacy columns.
- It is idempotent for SQLite and PostgreSQL. Runtime compatibility guards stay
  in place for mixed-version recovery environments.
- `/health` reports database state and requires migrations 0064, 0065, and
  0066; a healthy 6.6.0 response has `migrations.missing = []`.
- Backup manifests remain `teacher-backup-v1`. Restore is insert-missing-only,
  filters rows to the destination schema, and maps legacy backups to additive
  columns without overwriting existing rows.

## Security invariants

- The server is authoritative for grading. Before submit, learner responses do
  not include answer keys, explanations, or review sources.
- `education_admin` and `system_admin` alone cannot sign as a clinical teacher.
  An account may sign clinically only when it actually has the
  `clinical_teacher` role.
- Dual signing always uses two different accounts.
- Production secret/session hardening, AI de-identification and privacy rules,
  upload validation, and backup protections remain enabled.

## Release verification

The release workflow compiles Python, runs the complete unittest suite, checks
the browser JavaScript files, validates version/entrypoint/migration/health
contracts, then publishes the `Teacher-6.6.0-release` ZIP artifact. The ZIP
excludes Git metadata, bytecode, local databases, environment files, local
apply/fix scripts, and failure logs.
