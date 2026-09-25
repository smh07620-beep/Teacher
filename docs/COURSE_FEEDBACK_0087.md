# Course Feedback 0087

Migration `0087-course-feedback` adds a general learner-to-course feedback loop without mixing feedback into exam grades or PGY teacher assessment.

## Learner contract

- An authenticated learner can submit one editable feedback row per course.
- Rating is required and limited to `1..5`; comment is optional and bounded to 2000 characters.
- The course must be active and inside the learner's canonical learning scope. Cross-scope requests fail closed as not found.
- `GET /api/course-feedback/<course_id>` returns only the current learner's own saved feedback.
- `PUT /api/course-feedback/<course_id>` creates or updates that same learner/course row; repeated edits do not create duplicate responses.

## Management privacy boundary

`GET /api/course-feedback/<course_id>/summary` is restricted to `group_leader`, `education_admin`, and `system_admin` under their normal course scope. It returns only response count, average rating, and the 1–5 rating distribution. The management UI deliberately does not expose learner usernames or individual free-text comments.

## UI

Learners open `課程回饋` directly from a course card. The dialog reloads their prior answer and allows later edits. The Course / Material admin workspace lazily loads the anonymous aggregate only when a manager selects `查看回饋彙總`, avoiding unnecessary requests for every course.

Course feedback remains informational quality-improvement data. It does not modify completion, remediation, assignments, assessment scoring, RBAC, or PGY signing.
