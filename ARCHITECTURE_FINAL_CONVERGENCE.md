# Final Convergence ownership freeze

This document freezes the frontend ownership model after Phase 3 modularization and the Course Wizard modernization work.

## Rules

- `static/system-admin.js` is a legacy compatibility bundle. It must not receive new product logic.
- Canonical feature logic belongs in the extracted `static/admin-*.js`, learner modules, or dedicated workflow modules.
- `static/course-wizard-681.js` is the canonical Course Wizard UI/state owner.
- Course/exam creation is owned by `course_bundle_72.py` with session RBAC and retry-safe workflow IDs.
- Course Wizard material follow-ups are owned by `course_bundle_followup_73.py` and the shared `static/material-upload-client.js` background queue transport.
- `static/admin-compat-facade.js` is compatibility glue only. It may route old `window.*` / HTML `onclick` contracts to canonical owners, but must not contain business rules, RBAC, API orchestration, persistence, or upload logic.
- `professional_title` and `responsibility_tags` remain personnel/display metadata and must never become authorization inputs.
- Normal teaching workflows use session RBAC. AdminKey/elevation compatibility remains confined to legacy or sensitive system operations until separately retired.

## Canonical frontend owners

| Responsibility | Canonical owner |
| --- | --- |
| Course Wizard UI/state | `static/course-wizard-681.js` |
| Material background transport | `static/material-upload-client.js` |
| Workspace routing | `static/admin-workspace.js` |
| Result data/workspace/export | `static/admin-results-data.js`, `static/admin-results-workspace.js`, `static/admin-results-export.js` |
| Course/material management | `static/admin-course-material.js`, `static/admin-materials.js` |
| Question bank/editor/actions/panel | `static/admin-question-bank.js`, `static/admin-question-editor-ui.js`, `static/admin-question-actions.js`, `static/admin-question-panel.js` |
| Exam settings/review/publish | `static/admin-exam-settings.js` |
| People / announcements / system status | `static/admin-people.js`, `static/admin-announcements.js`, `static/admin-system.js` |
| PGY assessments | `static/admin-pgy-assessments.js` |
| Document templates | `static/admin-doc-templates.js` |
| External media | `static/admin-external-media.js` |
| Learner exam/result compatibility | `static/learner-exam-controls.js`, `static/learner-result-chart.js` |

## Retirement sequence

1. Keep `system-admin.js` loaded as a fallback while the compatibility facade shadows migrated entry points.
2. Prove all release checks and role/workflow acceptance paths with canonical owners.
3. Remove dead legacy implementations from `system-admin.js` in small deletion-only or wrapper-only PRs.
4. Retain the thin facade for one compatibility cycle so cached/older HTML `onclick` contracts continue to work.
5. Remove facade entries only after no live HTML or module references remain.

The final target is a small bootstrap/compatibility shell rather than a second implementation of any workflow.
