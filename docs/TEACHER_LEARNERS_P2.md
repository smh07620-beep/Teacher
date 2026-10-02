# P2 Teacher Learner Workspace

The first P2 teacher capability is a read-only **我的學員** projection embedded
inside the existing 評量與出題 workspace. It does not add a third teacher
top-level navigation item.

## Canonical API

`GET /api/training-command-center/teacher-learners`

The endpoint derives scope only from the authenticated session and canonical
permissions:

- `clinical_teacher` / `student.view_assigned`: learners explicitly linked by
  `pgy_assignments.teacher_username`;
- `group_leader` / `student.view_group`: learners in the leader's own group;
- `education_admin` / `student.view_all`: organization-wide teaching
  coordination read scope;
- a standalone `system_admin` does not receive clinical learner scope.

Browser-supplied learner, teacher, group, role, or evaluator identity never widens
the result.

## Projection

The read model returns learner identity plus PGY assignment counts and workflow
status counts such as pending teacher review, leader review, final confirmation,
completed assignments, and overdue assignments. It intentionally does **not**
invent a competency/mastery score and does not grant signing authority.

## UI

`static/teacher-learners-p2.js` mounts the roster under 評量與出題 →
目前工作. Existing flows remain the mutation owners:

- `查看考核紀錄` is shown only when the session already has
  `evaluation.review`;
- `進入 PGY 工作流程` delegates to the existing PGY teacher workflow.

## Release coverage

- `tests/test_teacher_learners_p2_20261002.py` protects backend scope and
  GET-only routing.
- `tests/playwright/teacher-learners-p2.spec.js` proves discoverability in the
  real system workspace and protects the two-item teacher primary navigation.
- The normal Teacher release, Product Golden Path, Playwright UI, and Windows
  Worker gates must remain green.
