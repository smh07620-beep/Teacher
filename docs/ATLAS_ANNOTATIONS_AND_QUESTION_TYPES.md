# Atlas annotations, hotspot questions, scenario questions

No new tables or environment variables. No schema migration.

## Atlas annotations (`atlas_items.annotation_json`)
`{"version":1,"marks":[{"id","label","detail","x","y","w","h"}]}` — fractions 0..1, max 30 marks.
Validated by `teacher_app/atlas/annotations.py`. Drawn once in the Atlas editor
(`static/atlas-annotations-1010.js`); learners zoom to a mark and read its detail.

## `atlas_hotspot` question
Teacher picks a published Atlas image + one mark. Server-only keys in `answer_config`:
`atlasItemId, correctMarkId, correctRegion, markLabel` (all in `ANSWER_SECRET_FIELDS`).
Learner answer `{x,y}`; graded by `annotations.point_in_region`. Region is refreshed
from the Atlas at attempt start and then snapshotted with the attempt.
Cannot be created by bulk/AI import.

## `scenario` question (情境題)
Question text = the case; `answer_config.steps = [{prompt, options[2..6], correctIndex}]`, 2–6 steps.
Learner answer = list of chosen indexes (null = unanswered). Correct only if every step is right.
`correctIndex` is in `ANSWER_SECRET_FIELDS`. Cannot be created by bulk/AI import. The inline
quick editor never alters the steps (it sends none; stored steps are kept).
Owners: `teacher_app/assessments/scenario.py`, `static/learner-scenario-question-1011.js`,
`static/admin-scenario-question-1011.js`.
