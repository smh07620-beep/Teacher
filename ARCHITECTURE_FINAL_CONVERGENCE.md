# Final Convergence ownership freeze

This document freezes the frontend ownership model after Phase 3 modularization and the Course Wizard modernization work.

## Rules

- `static/system-admin.js` is a legacy compatibility bundle. It must not receive new product logic.
- Canonical feature logic belongs in the extracted `static/admin-*.js`, learner modules, or dedicated workflow modules.
- `static/course-wizard-681.js` is the canonical Course Wizard UI/state owner.
- Course/exam creation is owned by `course_bundle_72.py` with session RBAC and retry-safe workflow IDs.
- Course Wizard material follow-ups are owned by `course_bundle_followup_73.py` and the shared `static/material-upload-client.js` background queue transport.
- `static/admin-compat-facade.js` is compatibility glue only. It may route old `window.*` / HTML `onclick` contracts to canonical owners, but must not contain business rules, RBAC, API orchestration, persistence, or upload logic.
- `static/assessment-681.js` is compatibility routing only after the 7.4 runtime convergence. It must not render a second exam/question UI or call mutation APIs.
- `static/question-authoring-ux-71.js` is a retired compatibility marker. Question editor presentation and mutation belong to the canonical `admin-question-*` owners.
- Unique blueprint-snapshot and item-analytics UI belongs to `static/assessment-advanced-74.js`; it must not own exam/question CRUD or AI question generation.
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
| AI-assisted question generation | `static/admin-ai-questions.js` |
| Exam settings/review/publish | `static/admin-exam-settings.js` |
| Assessment blueprint snapshots / item analytics | `static/assessment-advanced-74.js` |
| People / announcements / system status | `static/admin-people.js`, `static/admin-announcements.js`, `static/admin-system.js` |
| PGY assessments | `static/admin-pgy-assessments.js` |
| Document templates | `static/admin-doc-templates.js` |
| External media | `static/admin-external-media.js` |
| Learner exam/result compatibility | `static/learner-exam-controls.js`, `static/learner-result-chart.js` |

## Compatibility-only surfaces

- `static/system-admin.js`: shared compatibility state/helpers plus not-yet-retired fallbacks. No new product logic.
- `static/admin-compat-facade.js`: thin old-global routing only.
- `static/assessment-681.js`: cached/older `assessment681*` callers route to canonical assessment owners; no second UI.
- `static/question-authoring-ux-71.js`: retired marker for one compatibility cycle; no UI/API behavior.
- `getAdminKey()` in `system-admin.js`: compatibility header seam only; authorization remains server-side session RBAC.
- Local DOCX fallback state in `system-admin.js`: intentionally retained until its ownership is migrated and separately validated.

## Retirement sequence

1. Keep `system-admin.js` loaded as a fallback while the compatibility facade shadows migrated entry points.
2. Prove all release checks and role/workflow acceptance paths with canonical owners.
3. Remove dead legacy implementations from `system-admin.js` in small deletion-only or wrapper-only PRs.
4. Retain thin facade/router names for one compatibility cycle so cached/older HTML `onclick` contracts continue to work.
5. Remove facade/router files only after no live HTML or module references remain.

The final target is a small bootstrap/compatibility shell rather than a second implementation of any workflow.

## Final skeleton cleanup (7.4 RC)

- Public `/`, `/internal`, and `/pgy` pages no longer carry the retired `v575-manage-direct` markup; role-aware management entries remain the only public-to-management path.
- `system-admin.js` no longer owns course/material hub rendering, question-bank presentation, people management, system health UI, or learner controls. Those implementations live in their canonical extracted modules.
- `getAdminKey()` remains only as the session-RBAC compatibility header seam, and local DOCX fallback state remains intentionally preserved.
- Obsolete unconsumed HTTP routes retired here: legacy DOCX Atlas preview, legacy learning analytics, standalone media capability, legacy background-job status, and unused groups/training-areas catalog APIs. The shared `preview_docx_atlas()` parser remains because the canonical Atlas DOCX wizard imports it directly.
- Supported replacements are the Atlas DOCX import wizard, training command-center analytics, and `/api/material-jobs`. Public group cards remain static presentation data for this RC; a data-driven catalog is a separate future change rather than a release-candidate refactor.
- `/api/quiz-questions/batch-delete` and `/api/security/status` now have canonical frontend consumers.
- `static/teaching.css` is retired; `static/learner.css` is the single owner of the teaching layout classes.


## RC 7.5 workspace simplification

- `課程＋教材` 日常畫面不再顯示 STEP 1–4 教學卡；建立動作由 `＋ 建立教學內容` 統一承接。
- Course Wizard 仍是 canonical course bundle owner，但預設不佔據管理畫面；只有從 Studio 選擇「建立課程」才顯示。
- `admin-material-workspace` 保留為 hidden canonical upload executor，不再同時扮演日常維護 UI。
- MEGA/R2 搬移與背景 Worker 狀態移到 `system_admin` 專用、預設收合的「進階維護」；一般教學角色看不到。
- `getAdminKey()` compatibility seam 與 DOCX fallback state 本輪不變。
