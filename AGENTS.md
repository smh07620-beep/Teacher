# Codex project instructions — PGY RBAC

This repository is the PGY / medical laboratory technologist training and assessment system. Treat the following RBAC rules as project-level requirements for every related change.

## Current architecture

- Flask backend is primarily in `app.py`.
- Frontend is under `static/`, including `system-admin.js`, `system-core.js`, `system-learner.js`, `system-assessment.js`, `system-exam.js`, and `shared-core.js`.
- The existing `user_accounts.role` model currently uses legacy roles such as `learner`, `teacher`, and `manager`.
- Existing server-side role validation and frontend role labels must be migrated without breaking existing accounts.
- Keep the current SQLite/PostgreSQL compatibility unless a separate migration task explicitly changes the database architecture.

## Canonical roles

Use these role codes in new code:

- `student` — 學員
- `clinical_teacher` — 臨床教師
- `group_leader` — 組長
- `education_admin` — 教學管理者
- `system_admin` — 系統管理者
- `auditor` — 稽核／唯讀

Legacy compatibility during migration:

- `learner` -> `student`
- `teacher` -> `clinical_teacher`
- `manager` -> `education_admin`

Do not silently map `system_admin` to clinical signing privileges.

## Scope model

Authorization must consider both role and scope. Recommended canonical scopes:

- student: `self`
- clinical_teacher: `assigned_students`
- group_leader: `group`
- education_admin: `organization`
- system_admin: `system`
- auditor: `authorized_readonly`

A role alone must never grant access to every learner in the system.

## Required access rules

| Role | View | Create / modify | Sign / approve |
|---|---|---|---|
| student | Own assigned materials, exams, progress, evaluation results | Own answers, evidence, reflections, feedback | No |
| clinical_teacher | Assigned group and assigned trainees | Evaluation drafts, grading, teacher feedback | May sign only assigned trainees |
| group_leader | All trainees and teacher records in own group | Group materials, question bank, course scheduling, permitted group records | May countersign / review group records |
| education_admin | Cross-group teaching data and progress | Accounts, assignments, courses, evaluation templates | May perform final administrative confirmation |
| system_admin | System settings, accounts, permissions, audit records | Roles, permissions, service and system configuration | Must NOT replace a clinical teacher or sign professional clinical evaluations |
| auditor | Historical data within authorized scope | No | No |

## Non-negotiable security requirements

1. Enforce authorization on the Flask server. Frontend hiding alone is never sufficient.
2. Every write API must validate the authenticated user, canonical role, scope, and target resource.
3. `system_admin` may administer the system but cannot create, edit, or sign a clinical professional evaluation as the evaluator.
4. `auditor` is strictly read-only.
5. A student cannot read or modify another student's answers, evidence, reflection, progress, or evaluations.
6. A clinical teacher can access only explicitly assigned trainees unless an additional group-level permission is present.
7. A group leader is limited to the leader's group.
8. An education administrator may coordinate across groups but must not impersonate the clinical evaluator.
9. Signed/finalized evaluation data must not be silently overwritten. Corrections must use an explicit return/correction workflow and preserve the previous version.
10. Security-sensitive actions must create an append-only audit event containing actor, role, action, target, timestamp, and relevant before/after metadata when appropriate.
11. Never trust role, employee ID, group, evaluator identity, score, signature status, or authorization scope sent only from browser JavaScript.
12. Do not expose secrets, admin keys, database credentials, session secrets, or environment values to frontend code or logs.

## Evaluation workflow

Use this state model unless existing data requires a compatible extension:

`draft -> submitted -> teacher_signed -> leader_reviewed (when required) -> finalized`

Correction flow:

`teacher_signed/leader_reviewed/finalized -> returned_for_correction -> submitted -> ...`

Finalized records should be immutable through ordinary edit endpoints.

Recommended status labels shown to users:

- 未開始
- 學習中
- 待評核
- 待教師簽核
- 待複核
- 已完成
- 未通過需補訓
- 退回更正

## Permission naming

Prefer explicit permission constants instead of repeated string comparisons. Example permission vocabulary:

- `course.view`, `course.edit`
- `exam.take`, `exam.manage`
- `evaluation.submit`, `evaluation.review`, `evaluation.sign`, `evaluation.countersign`, `evaluation.finalize`
- `student.view_self`, `student.view_assigned`, `student.view_group`, `student.view_all`
- `user.manage`, `role.manage`, `audit.view`, `system.manage`

Centralize permission decisions in backend helper functions/decorators rather than scattering `if role == ...` across routes.

## Migration requirements

When implementing this RBAC model:

- Existing `learner`, `teacher`, and `manager` accounts must continue to log in during migration.
- Normalize legacy roles to canonical roles at the authorization boundary.
- Update account creation/edit validation, admin role selectors, labels, session user payloads, and API serialization.
- Add persistent assignment/scope data instead of relying only on a user's preferred group.
- Existing records must remain readable; do not delete or rewrite historical evaluation records destructively.
- Include a safe database migration path for both SQLite and PostgreSQL.

## Testing requirements

Add or update tests for at least these cases:

- student cannot read another student's data
- student cannot call admin/write/sign endpoints
- clinical teacher can access assigned trainee and cannot access unassigned trainee
- clinical teacher can sign assigned trainee evaluation
- group leader cannot operate outside own group
- education admin can manage cross-group teaching configuration but cannot impersonate clinical evaluator
- system admin can manage accounts/roles but cannot perform clinical evaluation signing
- auditor cannot mutate any protected resource
- finalized evaluation cannot be overwritten by normal edit API
- legacy roles still resolve to their canonical roles during migration

## Implementation style

- Make the smallest coherent change that preserves existing functionality.
- Prefer backward-compatible schema migrations.
- Keep authorization logic readable and testable.
- Do not weaken existing authentication/session protections to make RBAC easier.
- Before finishing an RBAC change, search for every use of legacy role values (`learner`, `teacher`, `manager`) and update or deliberately preserve it.
- Document any new tables, columns, environment variables, endpoints, and migration steps in the repository README or a dedicated `docs/` file.
