# Frontend JavaScript Ownership Map

Updated: 2026-10-03

This map records the remaining compatibility wrapper chains that intentionally reassign an existing frontend entrypoint. A wrapper may add presentation, filtering, metadata, or cleanup, but it must preserve and call the canonical implementation rather than becoming a second product owner.

## Reviewed wrapper chains

| Global/API | Canonical owner | Wrapper | Wrapper responsibility |
| --- | --- | --- | --- |
| `fetchAdminRecords` | `static/admin-results-data.js` | `static/admin-results-workspace.js` | Filter canonical records for the active results/teacher mode. |
| `renderAdminTable` | `static/admin-results-data.js` | `static/admin-results-workspace.js` | Add mode-aware presentation around the canonical results table. |
| `renderResultsAnalytics` | `static/admin-results-data.js` | `static/admin-results-workspace.js` | Add mode-aware analytics projection only. |
| `openMaterial` | `static/system-learner.js` | `static/teacher-media-subtitle-1014.js` | After the canonical viewer opens, attach an approved subtitle track when available. |
| `toggleQuizQuestionsPanel` | `static/admin-question-panel.js` | `static/teacher-content-tool-panels-710.js` | Preserve canonical panel opening and remove obsolete close controls afterward. |
| `renderAdminMaterials` | `static/admin-materials.js` | `static/content-audience-1014.js` | Add audience/scope presentation after the canonical material renderer. |
| `renderFilteredQuestionList` | `static/admin-question-editor-ui.js` | `static/content-audience-1014.js` | Decorate already-rendered question rows with audience presentation. |
| `loadQuizQuestionsIntoPanel` | `static/admin-question-actions.js` | `static/content-audience-1014.js` | Preserve canonical loading, then decorate resulting question rows. |
| `adminBuildQuestionPayload` | `static/admin-question-actions.js` | `static/review-links-66.js` | Add review-source metadata; it must not re-own question CRUD. |
| `buildSlideCardHTML` | `static/system-learner.js` | `static/learner-content-audience-1014.js` | Add learner-visible audience badges to canonical material cards. |
| `buildCourseMaterialRow` | `static/system-learner.js` | `static/learner-content-audience-1014.js` | Add learner-visible audience badges to canonical course-material rows. |
| `courseWizard681OpenCourse` | `static/course-wizard-681.js` | `static/course-wizard-runtime-fix-1014.js` | Prevent duplicate/re-entrant finish rendering and route through the canonical workspace router. |

## Duplicate owners removed in this audit

- `createAdminUserAccount` — canonical owner: `static/admin-people.js`. `roles-signing-66.js` now only supplies selected roles through `TeacherRoleSigning66.getCreateRoles()`.
- `fetchAdminMaterials` — canonical owner: `static/admin-materials.js`. `rbac-ui-681.js` no longer replaces it after an asynchronous profile request.

## Navigation ownership

- `static/admin-workspace.js` is the sole owner of `switchAdminWorkspace`, `toggleAdminModal`, workspace normalization, URL synchronization, and extension dispatch.
- `static/workspace-shell-70.js` is the sole structural owner of the **system-persona navigation tree**. It groups `people`, `system/worker/maintenance`, and `audit` using stable `data-admin-nav-group` slots.
- `static/worker-status-70.js` owns only the Worker button and Worker workspace renderer. It may insert that button into the canonical `operations` slot, but it must not rebuild the surrounding navigation.
- `static/system-admin-focus-1014.js` is presentation-only: it hides leaked teacher-owned controls and maintains the focus note. It must not call `replaceChildren()` on the navigation host.
- `static/product-convergence-101.js` may normalize labels and hide unexpected controls, but it must not structurally rebuild the system navigation.
- Deferred extension workspaces `worker`, `maintenance`, and `audit` must resolve a registered handler before visible workspace state changes. A previous assessment/AI section must never remain visible under a Worker header.
- Dynamic system navigation buttons use `data-csp-click="switchAdminWorkspace(...)"` and clear any direct `onclick` navigation property.
- `static/system-csp-actions.js` is the single delegated owner for `data-csp-click`; it invokes only the nearest element carrying that event attribute.
- Notification Center actions remain canonical server-generated links. Worker-offline actions target `workspace=worker&persona=system` and are regression-tested by an actual click-through.

## Guardrails

1. Do not add a new assignment to one of the globals above without updating this map and a regression test.
2. A wrapper captures the previous implementation once, calls it once, and limits itself to the responsibility documented above.
3. Network response timing, `setTimeout`, or transient DOM presence must never decide which implementation owns a global.
4. Do not attach both direct `onclick` navigation and `data-csp-click` to the same system navigation control.
5. Extension workspace deep links must wait for their registered handler or fail closed; they must never show a stale section from another workspace.


## Selector / dispatch collision audit

- System navigation uses one click path: `data-csp-click` → `static/system-csp-actions.js` → `switchAdminWorkspace(...)`. Dynamic system buttons explicitly clear `.onclick` before installing the CSP action.
- Auditor workspace entry also uses only the CSP path: its inherited `openTeachingMaterials()` action is replaced with `toggleAdminModal(true)`, and any native `.onclick` is cleared first.
- Worker notification actions are ordinary server-generated `<a href="/system?admin=1&workspace=worker&persona=system...">` links. They do not share the admin-navigation delegated selector.
- Teacher authoring capture handlers are scoped to the Teacher Content Studio (for example `[data-composer-question-next]`) and do not match `.admin-nav-btn`, Notification Center links, or Worker controls.
- Browser regression counts calls to `switchAdminWorkspace` when System and Worker buttons are clicked and requires exactly one dispatch per click.
