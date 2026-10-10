# Slide checkpoints (投影片小測驗)

Optional, teacher opt-in. A material with no checkpoint behaves exactly as before.

- Migration `0118-slide-checkpoints` (additive; SQLite/PostgreSQL):
  `slide_checkpoints` (question, options_json, correct_index, explanation, page_no, material_version, active)
  and `slide_checkpoint_answers` (first answer per learner per checkpoint = the learning record).
- API (`teacher_app/checkpoints/routes.py`):
  `GET /api/materials/<id>/checkpoints` (learner view; the right answer + explanation appear only after
  that learner answered), `GET .../checkpoints/manage`, `POST .../checkpoints`,
  `PATCH|DELETE /api/slide-checkpoints/<id>`, `POST /api/slide-checkpoints/<id>/answer`.
- RBAC: authoring needs `material.manage` within the material's group (education/system admin: any group);
  auditors cannot answer; learners need normal access to the material.
- Never blocks reading, paging or completion; not part of exam scores.
- Checkpoints are bound to the material version they were written for; after a new version they are hidden
  until the teacher re-applies them in the editor. Deleting a question keeps learners' answer rows.
- Frontend: `static/learner-slide-checkpoints-1011.js` (read-only observer of `slideViewerState`),
  `static/admin-slide-checkpoints-1011.js` (editor opened from the course hub material menu).
