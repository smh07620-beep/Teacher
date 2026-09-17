# Teacher 7.4 Runtime Convergence Audit

This audit distinguishes real duplicate implementations from intentionally separate responsibilities. The release rule is **one normal user-facing runtime owner per responsibility**. Compatibility names may remain only when required for cached/older callers; they may not render a second product UI or own business mutations.

## Audit result

| Area | Current canonical owner | Legacy / adjacent surface | Classification | Action |
| --- | --- | --- | --- | --- |
| Authentication / session | `teacher_app.auth` + session/RBAC adapters | root compatibility delegates | Converged | Keep thin delegates only |
| Workspace routing | `static/admin-workspace.js` | workspace shell presentation | Distinct responsibility | Keep |
| Course Wizard | `static/course-wizard-681.js`, `course_bundle_72.py`, `course_bundle_followup_73.py` | former `system-admin.js` implementation | Retired | Legacy implementation deleted |
| Course/material management | `static/admin-course-material.js`, `static/admin-course-material-hub.js`, `static/admin-materials.js` | former legacy hub/helper implementation | Converged | One visible management owner |
| Material upload | `static/admin-material-upload.js` + `static/material-upload-client.js` | Worker/background transport | Distinct responsibility | Keep both |
| Exam/category management | `static/admin-question-card.js`, `static/admin-question-bank.js`, `static/admin-question-panel.js`, `static/admin-exam-settings.js` | former `assessment-681.js` exam table/editor | Duplicate before 7.4 | Duplicate UI retired |
| Question CRUD / bulk actions | `static/admin-question-editor-ui.js`, `static/admin-question-actions.js`, `static/admin-question-panel.js` | former `assessment-681.js` drawer + `question-authoring-ux-71.js` overlay | Duplicate before 7.4 | Overlay file deleted |
| AI-assisted questions | `static/admin-ai-questions.js` | former `assessment-681.js` AI tab and legacy helpers | Duplicate before 7.4 | Legacy implementation deleted |
| Blueprint snapshots | `static/assessment-advanced-74.js` | formerly embedded in `assessment-681.js` | Unique capability | Extracted and retained |
| Item analytics | `static/assessment-advanced-74.js` | formerly embedded in `assessment-681.js` | Unique capability | Extracted and retained |
| Teacher content creation | `static/teacher-content-studio-71.js` + `static/teacher-content-composer-72.js` | hidden canonical material executor | Orchestration vs executor | Keep one visible launcher |
| Results / exports | `static/admin-results-data.js`, `static/admin-results-workspace.js`, `static/admin-results-export.js`, `static/admin-results-docx-fallback.js` | no second result workspace | Converged | Local DOCX fallback isolated |
| PGY clinical assessment form | `static/system-assessment.js` + canonical PGY APIs | `static/admin-pgy-assessments.js` | Distinct learner/clinical workflow vs administration | Do not merge |
| PGY workflow/signing | canonical PGY service/workflow + `static/pgy-workflow.js` | signing overlays | Distinct transition/UI layers | Keep |
| External media | `external_media_68.py` + `static/external-material-681.js` | `static/admin-external-media.js` | Feature runtime vs admin adapter | Keep |
| Atlas | `atlas_70.py` + `static/atlas-70.js` | DOCX import wizard | Browse/editor vs importer | Keep |
| DOCX templates/results | document template backend + `static/admin-doc-templates.js` / results export | `static/admin-results-docx-fallback.js` | Primary path + isolated compatibility fallback | Keep isolated fallback only |
| Worker/jobs | worker backend + `static/worker-status-70.js`, `static/admin-jobs.js` | material upload status | Operations vs authoring | Keep |
| Shared admin state | `static/admin-runtime-shared.js` | former `system-admin.js` shared state | Converged | UI/business logic prohibited here |
| `system-admin.js` | none | deleted | Retired | Must remain absent |
| `admin-compat-facade.js` | none | cached/old global routing | Compatibility shell | Keep thin and business-logic free for one cycle |

## 7.4 convergence decisions

1. The visible `assessment-681` application is retired. It must never hide `#admin-quiz-workspace`, create `#assessment-681-body`, or create a second question drawer.
2. Exam/category CRUD is canonical only in the `admin-question-*` / `admin-exam-settings.js` stack.
3. Question CRUD, delete, bulk delete, filters and inline editing are canonical only in `admin-question-editor-ui.js`, `admin-question-actions.js`, and `admin-question-panel.js`.
4. AI candidate generation/import is canonical only in `admin-ai-questions.js`.
5. Blueprint snapshots and item analytics live in `assessment-advanced-74.js` because those capabilities had no other frontend owner.
6. `assessment-681.js` remains temporarily as a no-API compatibility router for cached callers. The former `question-authoring-ux-71.js` no-op marker is no longer needed and is deleted.
7. `system-admin.js` has been fully retired: shared state moved to `admin-runtime-shared.js`; course/material hub, question card/presentation, people/account list, system status, and DOCX fallback moved to dedicated owners; already-extracted AI/question/doc-template/job/learner fallbacks were deleted rather than copied.
8. `pgy_frontend.py` rewrites the historical static HTML `system-admin.js` marker to `admin-runtime-shared.js` before response delivery, so the deleted bundle is not requested by browsers.

## Release gate added by this audit

A release candidate fails convergence if:

- `assessment-681.js` contains assessment UI rendering or mutation API paths;
- `assessment-advanced-74.js` calls AI generation or exam/question CRUD mutation endpoints;
- `static/system-admin.js` or `static/question-authoring-ux-71.js` exists;
- canonical question/exam/AI owner files lose their expected management functions;
- `admin-runtime-shared.js` grows product UI/business mutation ownership;
- a new product workflow is implemented in `admin-compat-facade.js`.
