# Teacher 6.8.1 Feature Exposure Matrix

This is the release audit for features beyond the legacy course/exam API.
Every API is either exposed by the normal UI, explicitly internal, or guarded
as an administrative implementation endpoint.  The administrative API is not
a supported hand-entered URL surface.

| Feature | Backend | UI / caller | RBAC | Tests | Status |
|---|---|---|---|---|---|
| Office/PDF preview | Worker + preview routes | material viewer | learner view; original blocked | Office regressions | Usable |
| Course/material bundle | courses/material APIs | course workspace wizard | elevated admin mutation | UI contract | Usable |
| Existing material linking | course/material/category APIs | course hub + material linker | elevated admin mutation | legacy integration | Usable |
| External YouTube/Shorts | external-media API | External Link drawer | elevated admin mutation | Shorts + drawer contract | Usable |
| Learning progress | learning-progress API | smart-learning reader | authenticated learner | progress regressions | Usable |
| ReviewSource | exam review projection | post-submit review link | server-authoritative | exam review tests | Usable |
| Exam workspace | legacy category/question APIs | unified assessment workspace | elevated admin mutation | UI contract | Usable |
| Admin elevation | elevation API | common `getAdminKey()` flow | eligible admin role + TTL | acceptance test | Usable |
| Worker/jobs/retry | worker APIs | material jobs panel | worker token / elevated admin | worker tests | Usable |
| Question Bank 2.0 drafts | `/api/question-bank/*` | **backend-only** service seam | elevated admin | acceptance tests | Internal/backend-only |
| Blueprint snapshots | `/api/exam-blueprints/*` | **backend-only** service seam | elevated admin | acceptance tests | Internal/backend-only |
| Item analytics | `/api/questions/<id>/analytics` | **backend-only** reporting seam | elevated admin | acceptance tests | Internal/backend-only |

## Deliberate internal surfaces

Question Bank 2.0 draft/review, blueprint, and analytics routes are retained as
server-side integration seams for the established assessment UI and automated
tests. They are not advertised as end-user controls until a complete review,
blueprint, and analytics editor is shipped together. This avoids misleading
teachers with partial or unsafe flows.  They require elevated administrative
access and are documented here rather than relying on hidden URLs.

## Removed dead modules

`static/media-player-68.js` and `static/admin-elevation-68.js` were never
loaded by HTML and duplicated active implementations. They were removed; the
active learner player and single-flight elevation paths live in the loaded
`smart-learning-67.js`/`system-admin.js` modules.
