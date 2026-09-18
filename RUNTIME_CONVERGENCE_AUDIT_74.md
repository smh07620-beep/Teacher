# Teacher 7.4 Runtime Convergence Audit

This audit distinguishes real duplicate implementations from intentionally separate responsibilities. The release rule is **one normal user-facing runtime owner per responsibility**. Compatibility names may remain for one cache/HTML compatibility cycle, but they may not render a second product UI or own business mutations.

## Audit result

| Area | Current canonical owner | Legacy / adjacent surface | Classification | Action |
| --- | --- | --- | --- | --- |
| Authentication / session | `teacher_app.auth` + session/RBAC adapters | root compatibility delegates | Converged | Keep thin delegates only |
| Workspace routing | `static/admin-workspace.js` | workspace shell presentation | Distinct responsibility | Keep |
| Course Wizard | `static/course-wizard-681.js`, `course_bundle_72.py`, `course_bundle_followup_73.py` | old `system-admin.js` wizard implementation | Already retired | Legacy implementation remains prohibited by tests |
| Course/material management | `static/admin-course-material.js`, `static/admin-materials.js` | shared helpers/fallback state in `system-admin.js` | Compatibility debt, not a second visible workspace | Continue deletion-only cleanup when helper ownership permits |
| Material upload | `static/admin-material-upload.js` + `static/material-upload-client.js` | Worker/background transport | Distinct responsibility | Keep both |
| Exam/category management | `static/admin-question-bank.js`, `static/admin-question-panel.js`, `static/admin-exam-settings.js` | former `assessment-681.js` exam table/editor | **Duplicate before 7.4** | Retire duplicate UI; compatibility router only |
| Question CRUD / bulk actions | `static/admin-question-editor-ui.js`, `static/admin-question-actions.js`, `static/admin-question-panel.js` | former `assessment-681.js` question drawer + `question-authoring-ux-71.js` overlay | **Duplicate before 7.4** | Retire duplicate drawer/overlay |
| AI-assisted questions | `static/admin-ai-questions.js` | former `assessment-681.js` AI tab | **Duplicate before 7.4** | Retire duplicate AI implementation |
| Blueprint snapshots | `static/assessment-advanced-74.js` | formerly embedded in `assessment-681.js` | Unique capability | Extract and keep one owner |
| Item analytics | `static/assessment-advanced-74.js` | formerly embedded in `assessment-681.js` | Unique capability | Extract and keep one owner |
| Teacher content creation | `static/teacher-content-studio-71.js` + `static/teacher-content-composer-72.js` | hidden legacy material executor | Orchestration vs executor | Keep one visible launcher; executor stays hidden |
| Results / exports | `static/admin-results-data.js`, `static/admin-results-workspace.js`, `static/admin-results-export.js` | legacy fallback seams | Compatibility only | No second visible result workflow |
| PGY clinical assessment form | `static/system-assessment.js` + canonical PGY APIs | `static/admin-pgy-assessments.js` | **Distinct** learner/clinical workflow vs administration | Do not merge |
| PGY workflow/signing | canonical PGY service/workflow + `static/pgy-workflow.js` | signing overlays | Distinct transition/UI layers | Keep |
| External media | `external_media_68.py` + `static/external-material-681.js` | `static/admin-external-media.js` | Feature runtime vs admin adapter | Keep |
| Atlas | `atlas_70.py` + `static/atlas-70.js` | DOCX import wizard | Browse/editor vs importer | Keep |
| DOCX templates/results | document template backend + `static/admin-doc-templates.js` / results export | local DOCX fallback state in `system-admin.js` | Compatibility fallback still required | Keep until separately migrated/tested |
| Worker/jobs | worker backend + `static/worker-status-70.js`, `static/admin-jobs.js` | material upload status | Operations vs authoring | Keep |
| `system-admin.js` | no new product ownership | shared compatibility state/helpers and not-yet-retired fallbacks | Compatibility shell | Delete only functions proven ownerless; keep `getAdminKey()` seam and DOCX fallback until migrated |
| `admin-compat-facade.js` | none | historical Course Wizard aliases | Removed | Raw HTML now calls `courseWizard681*` directly |

## 7.4 convergence decisions

1. The visible `assessment-681` application is retired. It must never hide `#admin-quiz-workspace`, create `#assessment-681-body`, or create a second question drawer.
2. Exam/category CRUD is canonical only in the `admin-question-*` / `admin-exam-settings.js` stack.
3. Question CRUD, delete, bulk delete, filters and inline editing are canonical only in `admin-question-editor-ui.js`, `admin-question-actions.js`, and `admin-question-panel.js`.
4. AI candidate generation/import is canonical only in `admin-ai-questions.js`.
5. Blueprint snapshots and item analytics move to `assessment-advanced-74.js` because those capabilities had no other frontend owner.
6. Retired compatibility assets are physically removed once all live callers are canonicalized: `assessment-681.js`, `question-authoring-ux-71.js`, `admin-compat-facade.js`, and `runtime-escape-guard-7111.js` no longer ship in the runtime.
7. The next physical cleanup target is dead fallback implementation inside `system-admin.js`; deletion must preserve the tested session-RBAC compatibility seam and local DOCX fallback state until their ownership is separately migrated.

## Release gate added by this audit

A release candidate fails convergence if:

- a removed compatibility asset is reintroduced instead of calling its canonical owner directly;
- `assessment-advanced-74.js` calls AI generation or exam/question CRUD mutation endpoints;
- canonical question/exam/AI owner files lose their expected management functions;
- a new product workflow is implemented in `system-admin.js` or another compatibility shim.

## Final skeleton cleanup result

The post-audit cleanup physically removes dead public navigation markup, retires obsolete unconsumed HTTP routes, connects batch-delete and security-status to canonical frontend owners, retires `teaching.css`, unifies `portal-v56.js` cache keys, and migrates the remaining course/question/people/system UI owners out of `system-admin.js`. The compatibility shell deliberately retains shared cache/state helpers, `getAdminKey()` as a non-secret session-RBAC header seam, and the tested local DOCX fallback only.
