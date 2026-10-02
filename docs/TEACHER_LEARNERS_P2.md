# P2 Teacher Workflow

P2 stays inside the existing two teacher jobs: **教材與課程** and **評量與出題**. It does not add another teacher top-level navigation item.

## 我的學員

`GET /api/training-command-center/teacher-learners` is the canonical read-only roster projection. Scope is derived only from the authenticated session: clinical teachers see explicitly assigned PGY learners, group leaders see their own group, education administrators receive organization-wide teaching coordination read scope, and a standalone system administrator receives no clinical learner scope.

## 臨床技能評核

The roster delegates writes to the existing canonical PGY assessment center and `POST /api/pgy-assessments`. Learner/evaluator identity is resolved again on the server, every required 1–5 rating is mandatory, duplicate in-flight saves are blocked, and a successful save emits `pgy:assessment-saved`. P2 then offers **返回我的學員並更新** and invalidates its read caches.

## 能力追蹤

`GET /api/training-command-center/teacher-competency` reuses formal PGY assessments and PGY assignment completion. It does not invent a mastery score.

## 教學分析

`GET /api/training-command-center/teacher-analytics` is a teacher-only wrapper around the canonical learning analytics projection. It uses the same server-derived learner scope across existing material progress, exam records, PGY assignments and formal PGY assessments. It is descriptive only: no AI mastery score or prediction.

## Release coverage

P2 is release-promoted as a single teacher flow while remaining inside the two
primary teacher jobs. The real browser path begins in **教材與課程**, switches
through the canonical **評量與出題** navigation, completes a scoped clinical
assessment, returns to **我的學員**, and verifies both **能力追蹤** and **教學分析**.

- `tests/test_teacher_learners_p2_20261002.py`: roster scope.
- `tests/test_pgy_clinical_assessment_scope_p2.py`: clinical write/read scope, server-derived identities and audit.
- `tests/test_teacher_competency_p2.py`: competency boundary.
- `tests/test_teacher_analytics_p2.py`: analytics boundary.
- `tests/playwright/teacher-learners-p2.spec.js`: deterministic P2 browser loop.
- `tests/playwright/teacher-workflow-p2-real-flask.spec.js`: real Chromium → Flask → SQLite full teacher workflow.
