# Saved Learning Items 0088

Migration `0088-saved-learning-items` adds cross-device save-for-later markers for courses and uploaded materials.

## Contract

- Saved items are keyed by authenticated `username + item_type + item_id`.
- Supported item types are `course` and `material`.
- Saving a new item requires the target to be active and inside the actor's canonical learning scope.
- Removing a marker only deletes that actor's own marker and does not modify the learning item.
- `GET /api/saved-learning-items` returns at most 200 currently visible saved items; stale or newly unauthorized markers are not exposed.
- `PUT /api/saved-learning-items/<item_type>/<item_id>` accepts `{ "saved": true|false }`.

## UI

The learner course center shows `☆ 稍後閱讀` / `★ 已收藏` on uploaded materials and `☆ 收藏課程` on courses. A `我的收藏` shelf lists account-synchronized items for the current learning area/group and provides direct navigation or removal.

## Separation from completion and page position

The existing `static/teaching.js` page bookmark remains browser-local `localStorage` state. It remembers the last page only. Saved-learning markers are server-side convenience state. Neither mechanism changes material completion, assignment state, remediation, exam scores, or authorization.
