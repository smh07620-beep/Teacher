# General Learning Assignments (0083)

Migration `0083-learning-assignments` adds the canonical assignment model for general course learning. It is intentionally separate from the PGY clinical assignment/signing state machine: general course assignment never grants or replaces clinical evaluation signing authority.

## Purpose

The learner portal historically used the account's preferred training area and group as the compatibility definition of "my learning". That remains the fallback for accounts without formal assignments. Once at least one active general learning assignment exists for the signed-in account, the personalized dashboard switches to assignment-driven scope.

Only assignments with `required=true` contribute to the required material/exam completion denominator and pending-course task list. Assignments with `required=false` remain visible as assigned courses but do not lower the required completion percentage.

## Authorization

The explicit permission is `learning.assign`: group leaders are limited to whole-group assignments in their own group, while education/system administrators may manage individual, group, or organization-wide general-learning assignments. Clinical teachers do not receive this permission by default. PGY signing remains governed by the existing clinical workflow.

## HTTP surface

- `GET /api/learning-assignments/mine`
- `GET /api/learning-assignments?area=...&group=...`
- `POST /api/learning-assignments`
- `PATCH /api/learning-assignments/<assignment_id>`

Create/update actions write append-only general audit events. Cancellation is non-destructive and preserves prior learning records.

## Learner projection

`GET /api/dashboard/me` keeps the established `scope={area,group}` shape and reports `scopeSource=assignments` when active assignments exist, otherwise `scopeSource=profile` for the preferred-area/group compatibility fallback. Assignment-driven responses include `requiredAssignments`, `overdueAssignments`, and `pendingCourses`. Learner task surfaces de-duplicate exams linked to a pending assigned course.

## Admin UI

The canonical Course / Material workspace (`static/admin-course-material.js`) exposes `指派學習` when the actor has assignment access. It supports group, individual-user and organization-wide targets, required/elective classification, due date, and non-destructive cancellation. Group leaders are deliberately limited to their own whole-group target; broader target types fail closed on the server.
