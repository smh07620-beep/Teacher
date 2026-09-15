# Teacher 6.8.1 Feature Exposure Matrix

This is the release audit for features beyond the legacy course/exam API.
Every API is either exposed by the normal UI, explicitly internal, or guarded
as an administrative implementation endpoint.  The administrative API is not
a supported hand-entered URL surface.

| Feature | Backend | UI / caller | RBAC | Tests | Status |
|---|---|---|---|---|---|
| Office/PDF preview | Worker + preview routes | material viewer | learner view; original blocked | Office regressions | Usable |
| Course/material bundle | courses/material APIs | course workspace wizard | session RBAC mutation | UI contract | Usable |
| Existing material linking | course/material/category APIs | course hub + material linker | session RBAC mutation | legacy integration | Usable |
| External YouTube/Shorts | external-media API | `external-material-681.js` direct-create drawer | session RBAC mutation | provider + direct-create tests | Usable |
| Learning progress | learning-progress API | smart-learning reader | authenticated learner | progress regressions | Usable |
| ReviewSource | exam review projection | post-submit review link | server-authoritative | exam review tests | Usable |
| Exam workspace | legacy category/question APIs | unified assessment workspace | session RBAC mutation | UI contract | Usable |
| Admin elevation | elevation API | automatic retry only for account/storage/backup/destructive system actions | privileged role + 15 min TTL | elevation boundary tests | Usable |
| Worker/jobs/retry | worker APIs | material jobs panel | worker token / session RBAC | worker tests | Usable |
| Question Bank 2.0 drafts | `/api/question-bank/*` | `assessment-681.js` 題庫／AI 出題／Review queue | session RBAC | question-bank integration + UI contract | Usable |
| Blueprint snapshots | `/api/exam-blueprints/*` | `assessment-681.js` 出題藍圖 tab | session RBAC | quota + UI payload tests | Usable |
| Item analytics | `/api/questions/<id>/analytics` | `assessment-681.js` 題目分析 tab | session RBAC | analytics contract tests | Usable |

## Deliberate internal surfaces

Worker orchestration, job retry, raw storage adapters, and background media
processing remain internal or elevated implementation surfaces.  The three
assessment APIs above are normal teacher-facing workflows through the loaded
five-tab assessment workspace; they are no longer classified as internal-only.

## Removed dead modules

`static/media-player-68.js` and `static/admin-elevation-68.js` were never
loaded by HTML and duplicated active implementations. They were removed; the
active learner player and sensitive elevation bridge live in the loaded
`smart-learning-67.js`/`sensitive-elevation-69.js` modules.
