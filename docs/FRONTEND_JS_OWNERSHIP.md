# Frontend JavaScript Ownership Map

Updated: 2026-10-03

This map records the remaining compatibility wrapper chains that intentionally reassign an existing frontend entrypoint. A wrapper may add presentation, filtering, metadata, or cleanup, but it must preserve and call the canonical implementation rather than becoming a second product owner.

## Reviewed wrapper chains

| Global/API | Canonical owner | Wrapper | Wrapper responsibility |
| --- | --- | --- | --- |
| `fetchAdminRecords` | `static/admin-results-data.js` | `static/admin-results-workspace.js` | Filter canonical records for the active results/teacher mode. |
| `renderAdminTable` | `static/admin-results-data.js` | `static/admin-results-workspace.js` | Add mode-aware presentation around the canonical results table. |
| `renderResultsAnalytics` | `static/admin-results-data.js` | `static/admin-results-workspace.js` | Add mode-aware analytics projection only. |
| `openMaterial` | `static/system-learner.js` | `static/smart-learning-67.js` → `static/teacher-media-subtitle-1014.js` | Smart Learning adds progress/external-media reader behavior, then subtitle integration attaches an approved track; both preserve the previous implementation. |
| `toggleQuizQuestionsPanel` | `static/admin-question-panel.js` | `static/teacher-content-tool-panels-710.js` | Preserve canonical panel opening and remove obsolete close controls afterward. |
| `renderAdminMaterials` | `static/admin-materials.js` | `static/content-audience-1014.js` | Add audience/scope presentation after the canonical material renderer. |
| `renderFilteredQuestionList` | `static/admin-question-editor-ui.js` | `static/content-audience-1014.js` | Decorate already-rendered question rows with audience presentation. |
| `loadQuizQuestionsIntoPanel` | `static/admin-question-actions.js` | `static/content-audience-1014.js` | Preserve canonical loading, then decorate resulting question rows. |
| `adminBuildQuestionPayload` | `static/admin-question-actions.js` | `static/review-links-66.js` | Add review-source metadata; it must not re-own question CRUD. |
| `buildSlideCardHTML` | `static/system-learner.js` | `static/learner-content-audience-1014.js` | Add learner-visible audience badges to canonical material cards. |
| `buildCourseMaterialRow` | `static/system-learner.js` | `static/learner-content-audience-1014.js` | Add learner-visible audience badges to canonical course-material rows. |
| `courseWizard681OpenCourse` | `static/course-wizard-681.js` | `static/course-wizard-runtime-fix-1014.js` | Prevent duplicate/re-entrant finish rendering and route through the canonical workspace router. |
| `markMaterialComplete` | `static/system-learner.js` | `static/teaching.js` → `static/learner-reading-progress-f2.js` | Canonical owner remains the legacy fallback writer and now exposes read/sync helpers for the lexical completion map. Teaching enforces homepage-linked identity and reads completion through that owner; F2 intercepts automatically tracked PDF/PPT/media so they use server-derived `/api/learning-progress` evidence, sync current-version completion back to the owner, and leave unsupported formats on the legacy fallback. |
| `renderCourseOverview` | `static/system-learner.js` stable dispatcher | `static/teaching.js` registers `TeachingCourseOverview66.render` → `static/learner-reading-progress-f2.js` | Teaching provides the ordered/searchable course presentation without replacing the global. F2 wraps the stable dispatcher only to repaint canonical server-derived reading progress after the canonical render completes. |

## Classic-script compatibility chains

These are not separate product owners, but classic scripts can reassign bare globals even without writing `window.<name>`. They therefore follow the same ownership rules and are part of the audit contract.

| Global/API | Canonical owner | Wrapper chain | Wrapper responsibility |
| --- | --- | --- | --- |
| `adminQuestionEditFormHTML` | `static/admin-question-editor-ui.js` | `static/review-links-66.js` | Preserve the canonical question editor HTML and append review-source fields only. |
| `renderQuestions` | `static/system-exam.js` | `static/review-links-66.js`, `static/learner-study-exam-loop-1032.js` | Preserve learner exam rendering, then inject review-source presentation and atlas re-read hints. |
| `renderSlidesGrid` | `static/system-learner.js` | `static/review-links-66.js` → `static/learner-reading-progress-f2.js` | Review-links resolves a pending review deep-link. F2 then refreshes `/api/learning-progress` and repaints server-derived reading/completion state after the canonical grid render. |
| `teachingSavePage` | `static/teaching.js` | `static/teaching.js` reader-next wrapper → `static/review-links-66.js` review-context wrapper | Save the page once, then synchronize reader-next state and review context. |
| `teachingNextMaterial` | `static/teaching.js` | `static/teaching.js` sequential-reader wrapper | Block next-material navigation until the current material is completed; no second persistence owner. |
| `switchDynamicCategory` | `static/system-exam.js` | `static/teaching.js` empty-exam wrapper, `static/learner-study-exam-loop-1032.js` | Prevent an empty exam from creating/entering an attempt; otherwise call the canonical exam switch once; then restore the last-result card. |
| `buildCourseExamRow` | `static/system-learner.js` | `static/teaching.js` empty-exam presentation wrapper, `static/learner-study-exam-loop-1032.js` pass/fail badge wrapper | Render zero-question exams as not-ready instead of actionable; add pass/fail status and retake hint. |
| `renderAdminQuizCategories` / `paintAdminQuizCategories` | `static/admin-question-bank.js` | `static/teacher-ui-resilience-1014.js` | Synchronize assessment scope and add empty-state recovery without owning question CRUD or fetch policy. |

## Duplicate owners removed in this audit

- `createAdminUserAccount` — canonical owner: `static/admin-people.js`. `roles-signing-66.js` now only supplies selected roles through `TeacherRoleSigning66.getCreateRoles()`.
- `fetchAdminMaterials` — canonical owner: `static/admin-materials.js`. `rbac-ui-681.js` no longer replaces it after an asynchronous profile request.
- `markMaterialComplete` — the duplicate POST implementation was removed from `static/teaching.js`; `static/system-learner.js` is the only writer and exposes `LearnerMaterialProgress.complete` for presentation wrappers.
- `renderCourseOverview` — `static/teaching.js` no longer replaces the global renderer. `static/system-learner.js` owns a stable dispatcher and shared finalizer; Teaching registers a presenter through `TeachingCourseOverview66`.

## CI-enforced sole owners

These globals have one mutation owner. Callers may invoke them, but no compatibility layer may replace them unless this table is deliberately changed in the same review.

| Global/API | Canonical owner |
| --- | --- |
| `switchAdminWorkspace` | `static/admin-workspace.js` |
| `toggleAdminModal` | `static/admin-workspace.js` |
| `createAdminUserAccount` | `static/admin-people.js` |
| `fetchAdminMaterials` | `static/admin-materials.js` |


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
6. Bare classic-script reassignments (for example `renderQuestions = function...`) count as ownership changes exactly like `window.renderQuestions = ...`; they must be documented and guarded.
7. A document-wide `MutationObserver` (`document.body` / `document.documentElement` with `childList + subtree`) is CI-controlled. New broad observers must be added to the ownership guard with an explicit selector filter, one-shot disconnect, or documented compatibility reason.
8. A new capture handler for `.admin-nav-btn` is prohibited unless it is explicitly registered as a navigation-interception owner; structural navigation remains owned by the workspace router/shell.
9. Any dynamically created system navigation control using `data-csp-click="switchAdminWorkspace(...)"` must clear a pre-existing `onclick` property/attribute first.


## Selector / dispatch collision audit

- System navigation uses one click path: `data-csp-click` → `static/system-csp-actions.js` → `switchAdminWorkspace(...)`. Dynamic system buttons explicitly clear `.onclick` before installing the CSP action.
- Auditor workspace entry also uses only the CSP path: its inherited `openTeachingMaterials()` action is replaced with `toggleAdminModal(true)`, and any native `.onclick` is cleared first.
- Worker notification actions are ordinary server-generated `<a href="/system?admin=1&workspace=worker&persona=system...">` links. They do not share the admin-navigation delegated selector.
- Operational Incident actions rendered by `static/worker-status-70.js` are ordinary `<a href>` navigation. They never use `data-csp-click`, `.onclick`, or `.admin-nav-btn`; Worker incidents use in-page anchors, Storage incidents enter the system workspace, and AI incidents enter teacher-owned workspaces only when the current account has teaching capability.
- Teacher authoring capture handlers are scoped to the Teacher Content Studio (for example `[data-composer-question-next]`) and do not match `.admin-nav-btn`, Notification Center links, or Worker controls.
- Browser regression counts calls to `switchAdminWorkspace` when System and Worker buttons are clicked and requires exactly one dispatch per click.

## Request pipeline middleware

`static/api-client.js` owns `window.fetch`; features add behaviour only through `AppApiClient.use(name, handler, priority)` and never reassign `window.fetch`. Registered middleware, in run order (lower priority number runs first):

| Priority | Name | File | Responsibility |
| --- | --- | --- | --- |
| 50 | `api-get-dedupe-1007` | `static/api-get-dedupe-1007.js` | Share identical same-origin read-only GETs (course/slide lists, learning progress, command-center progress and analytics, `/api/auth/me`, `/api/auth/profile`) that many page scripts request while the page boots. Concurrent callers share one network call; a successful answer is reused for 3 s except by `cache: no-store`/`reload`/`no-cache` callers, which only join a request still in flight. Any `/api/` write clears everything before and after it runs. Callers with an `AbortSignal` are never shared. Failed answers are never kept. |
| 100 | `teacher-content-latency-712` | `static/teacher-content-latency-712.js` | Cache and de-duplicate the exam-list endpoints (`/api/quiz-categories*`); these paths are intentionally absent from the shared allow-list above. |
| 200 | `review-source-66` | `static/review-links-66.js` | Review-link source handling. |
| 300 | `sensitive-elevation-69` | `static/sensitive-elevation-69.js` | Sensitive-action elevation retry. |

To share another read endpoint, add its exact path to `SHARED_PATHS` in `static/api-get-dedupe-1007.js` and extend `tests/js/api-get-dedupe-1007.test.js`; never add polling, job-status, login, upload, exam-taking or signing endpoints.
