# PGY RBAC v1 implementation specification

## Goal

Introduce a six-role role-based access control model with explicit scope and auditable evaluation signing, while preserving compatibility with existing accounts and records.

## Roles

| Code | Label | Scope default |
|---|---|---|
| `student` | 學員 | `self` |
| `clinical_teacher` | 臨床教師 | `assigned_students` |
| `group_leader` | 組長 | `group` |
| `education_admin` | 教學管理者 | `organization` |
| `system_admin` | 系統管理者 | `system` |
| `auditor` | 稽核／唯讀 | `authorized_readonly` |

Legacy aliases: `learner -> student`, `teacher -> clinical_teacher`, `manager -> education_admin`.

## Recommended schema additions

Do not infer authorization scope only from `preferred_group`.

### `user_accounts`

Keep existing columns and add, if practical:

- `role` canonical role code
- `scope_type` text
- `scope_ref` nullable text (group/org/scope identifier)

If changing `role` values in-place is risky, normalize legacy values in application code first and migrate stored values later.

### `trainee_assignments`

Suggested fields:

- `id`
- `trainee_username` or stable trainee account id
- `teacher_username` or stable teacher account id
- `group_key`
- `active`
- `starts_at`
- `ends_at`
- `created_at`
- `created_by`

This table is the primary source for `clinical_teacher -> assigned_students` authorization.

### `evaluation_signoffs`

Suggested fields:

- `id`
- `evaluation_id`
- `stage` (`teacher_signed`, `leader_reviewed`, `finalized`)
- `signer_username`
- `signer_role`
- `signed_at`
- `signature_metadata_json`
- `supersedes_signoff_id` nullable

Do not encode a signature only as a mutable boolean on the evaluation row.

### `audit_events`

Suggested fields:

- `id`
- `created_at`
- `actor_username`
- `actor_role`
- `action`
- `target_type`
- `target_id`
- `scope_json`
- `before_json` nullable
- `after_json` nullable
- `request_id` nullable

Audit rows should be append-only through normal application endpoints.

## Backend authorization layer

Implement a centralized role normalizer and permission checker in `app.py` or a small dedicated module if splitting is safe.

Suggested functions:

```python
LEGACY_ROLE_ALIASES = {
    "learner": "student",
    "teacher": "clinical_teacher",
    "manager": "education_admin",
}

CANONICAL_ROLES = {
    "student",
    "clinical_teacher",
    "group_leader",
    "education_admin",
    "system_admin",
    "auditor",
}


def normalize_role(role: str) -> str:
    role = (role or "student").strip().lower()
    return LEGACY_ROLE_ALIASES.get(role, role if role in CANONICAL_ROLES else "student")
```

Create reusable checks for:

- authenticated user
- canonical role
- permission
- resource scope
- assignment/group relationship
- immutable/finalized state

Avoid using `X-Admin-Key` as the only authorization mechanism for user-facing role actions. If it must remain for legacy administration, place RBAC checks on top and plan its deprecation.

## Permission matrix

### Student

Allowed:

- view own assigned curriculum/material/exams/progress/evaluation result
- submit own exam answers
- create/update own learning evidence before locking
- create/update own reflection and feedback
- submit own evaluation-related learner input

Denied:

- any other trainee data
- grading
- professional evaluation edits
- signing/countersigning/finalizing
- account/role/system administration

### Clinical teacher

Allowed within assignment scope:

- view assigned trainee teaching records
- grade assigned trainees
- create/edit evaluation drafts and feedback
- sign assigned trainee evaluations

Denied:

- unassigned trainees
- group-wide administrative authority unless separately granted
- final administrative confirmation
- account/role/system settings

### Group leader

Allowed within own group:

- view all group trainees and teacher records
- manage permitted group materials/question bank/course schedule
- review/countersign group records

Denied:

- other groups
- system-level role/service configuration
- impersonating original clinical evaluator

### Education admin

Allowed:

- cross-group teaching data
- account assignment operations
- course/evaluation template administration
- final administrative confirmation

Must preserve original clinical evaluator identity. Administrative finalization is not a replacement clinical signature.

### System admin

Allowed:

- account, role, permission, integration and system configuration
- audit visibility per policy

Explicitly denied:

- acting as clinical evaluator
- clinical teacher signature
- rewriting signed clinical assessment content

### Auditor

Read-only in authorized scope. All mutation routes return 403.

## Evaluation state machine

Recommended states:

- `draft`
- `submitted`
- `teacher_signed`
- `leader_reviewed`
- `finalized`
- `returned_for_correction`

Transition rules:

- student/authorized author may move draft -> submitted
- assigned clinical teacher may review/sign submitted -> teacher_signed
- group leader may countersign teacher_signed -> leader_reviewed when configured
- education admin may finalize the required prior state -> finalized
- authorized reviewer/admin may return a record for correction, but must not erase prior signoff/audit history
- finalized records are immutable via normal update endpoints

## Frontend changes

Update at minimum:

- account role selector in `static/system.html`
- role labels and account rendering in `static/system-admin.js`
- authenticated user handling in `static/shared-core.js`, `static/login.js`, and related bootstrapping code
- hide/disable actions based on role for usability, but keep backend as the security boundary

Suggested role labels:

```js
const roleLabel = {
  student: '學員',
  clinical_teacher: '臨床教師',
  group_leader: '組長',
  education_admin: '教學管理者',
  system_admin: '系統管理者',
  auditor: '稽核／唯讀',
  learner: '學員',
  teacher: '臨床教師',
  manager: '教學管理者'
};
```

## API migration targets found in current code

The current backend validates account roles against `learner`, `teacher`, `manager`. Replace that with canonical validation plus legacy normalization while preserving old accounts.

The current admin frontend also renders only `learner`, `teacher`, `manager`; extend the UI to all six canonical roles.

## Suggested implementation sequence for Codex

1. Add canonical role constants, role normalization and permission helpers.
2. Update session/auth user serialization to return canonical role while retaining a legacy-compatible field only if truly needed.
3. Update account create/edit validation to accept six canonical roles and legacy aliases.
4. Add assignment/scope persistence and helper queries.
5. Protect existing API routes by permission and scope, starting with users/admin, records/evaluations, course/material/question management, and progress endpoints.
6. Add evaluation state/signoff persistence and immutable finalization rules.
7. Add audit events for role/account changes, evaluation signing/finalization/correction, and sensitive administrative writes.
8. Update frontend role selector, labels, navigation and action visibility.
9. Add migration/backfill path for old role values.
10. Add automated authorization tests.

## Acceptance criteria

The change is complete only when all are true:

- Existing legacy accounts still log in.
- New accounts can use all six roles.
- Role returned by backend is normalized consistently.
- Student cannot access another student's protected data by changing URL/query/body fields.
- Clinical teacher cannot access or sign an unassigned trainee.
- Group leader cannot cross group scope.
- Education admin can perform teaching administration/final confirmation without being recorded as clinical evaluator.
- System admin cannot call clinical signing endpoint successfully.
- Auditor cannot mutate any protected resource.
- Finalized evaluation cannot be overwritten by ordinary update APIs.
- Signing and correction events are auditable.
- Frontend reflects role permissions but backend remains authoritative.
