# Final Convergence ownership freeze

This document freezes the frontend ownership model after Phase 3 modularization and the Teacher 7.4 runtime-convergence work.

## Rules

- `static/system-admin.js` is deleted. Product/runtime ownership must not be recreated there.
- Shared cross-module cache/state helpers live in `static/admin-runtime-shared.js`; that file must not grow product UI or business mutations.
- Canonical feature logic belongs in the extracted `static/admin-*.js`, learner modules, or dedicated workflow modules.
- `static/course-wizard-681.js` is the canonical Course Wizard UI/state owner.
- Course/exam creation is owned by `course_bundle_72.py` with session RBAC and retry-safe workflow IDs.
- Course Wizard material follow-ups are owned by `course_bundle_followup_73.py` and the shared `static/material-upload-client.js` background queue transport.
- `static/admin-compat-facade.js` is compatibility glue only. It may route old `window.*` / HTML `onclick` contracts to canonical owners, but must not contain business rules, RBAC, API orchestration, persistence, or upload logic.
- `static/assessment-681.js` is compatibility routing only after the 7.4 runtime convergence. It must not render a second exam/question UI or call mutation APIs.
- `static/question-authoring-ux-71.js` is deleted. Question editor presentation and mutation belong to the canonical `admin-question-*` owners.
- Unique blueprint-snapshot and item-analytics UI belongs to `static/assessment-advanced-74.js`; it must not own exam/question CRUD or AI question generation.
- `professional_title` and `responsibility_tags` remain personnel/display metadata and must never become authorization inputs.
- Normal teaching workflows use session RBAC. `getAdminKey()` is only a compatibility header seam in `static/admin-runtime-shared.js`; authorization remains server-side.

## Canonical frontend owners

| Responsibility | Canonical owner |
| --- | --- |
| Shared admin cache/state seam | `static/admin-runtime-shared.js` |
| Course Wizard UI/state | `static/course-wizard-681.js` |
| Material background transport | `static/material-upload-client.js` |
| Workspace routing | `static/admin-workspace.js` |
| Result data/workspace/export | `static/admin-results-data.js`, `static/admin-results-workspace.js`, `static/admin-results-export.js`, `static/admin-results-docx-fallback.js` |
| Course/material management | `static/admin-course-material.js`, `static/admin-course-material-hub.js`, `static/admin-materials.js` |
| Question category/presentation/editor/actions/panel | `static/admin-question-card.js`, `static/admin-question-presentation.js`, `static/admin-question-bank.js`, `static/admin-question-editor-ui.js`, `static/admin-question-actions.js`, `static/admin-question-panel.js` |
| AI-assisted question generation | `static/admin-ai-questions.js` |
| Exam settings/review/publish | `static/admin-exam-settings.js` |
| Assessment blueprint snapshots / item analytics | `static/assessment-advanced-74.js` |
| People / account list | `static/admin-people.js`, `static/admin-people-accounts.js` |
| Announcements | `static/admin-announcements.js` |
| System status / storage actions | `static/admin-system-status.js`, `static/admin-system.js` |
| PGY assessments | `static/admin-pgy-assessments.js` |
| Document templates | `static/admin-doc-templates.js` |
| External media | `static/admin-external-media.js` |
| Learner exam/result compatibility | `static/learner-exam-controls.js`, `static/learner-result-chart.js` |

## Compatibility-only surfaces

- `static/admin-compat-facade.js`: thin old-global routing only.
- `static/assessment-681.js`: cached/older `assessment681*` callers route to canonical assessment owners; no second UI.
- `getAdminKey()` in `static/admin-runtime-shared.js`: compatibility header seam only; authorization remains server-side session RBAC.
- The original `system.html` source still contains the historical `system-admin.js` script marker, but `pgy_frontend.py` rewrites that marker to `admin-runtime-shared.js` before the browser receives `/system` or `/system.html`. The deleted file is therefore never requested at runtime.
- Local DOCX fallback state moved to `static/admin-results-docx-fallback.js`; primary export still uses the server-managed group template path.

## Completed retirement sequence

1. Course Wizard ownership was extracted and the legacy implementation removed.
2. Duplicate assessment/question/AI UI was converged onto the canonical admin stack.
3. Shared admin cache/state was moved to `admin-runtime-shared.js`.
4. Course/material hub, question card/presentation, people/account list, system overview, and DOCX fallback were moved to dedicated owners.
5. `static/system-admin.js` was physically deleted.
6. `static/question-authoring-ux-71.js` was physically deleted after its overlay behavior had already been retired.
7. `admin-compat-facade.js` and `assessment-681.js` remain only where cached/older HTML/global contracts still require thin routing.

The target state is now one runtime owner per responsibility, plus only thin compatibility routing where a live cached caller can still exist.
