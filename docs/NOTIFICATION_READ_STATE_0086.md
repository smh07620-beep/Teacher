# Notification read state (0086)

Migration `0086-notification-read-state` adds cross-device read/unread state to the existing Notification Center without creating a second notification-content store.

## Ownership

- Course assignments, exams/remediation, PGY tasks and announcements remain the canonical content owners.
- `notification_read_state` stores only `username`, a stable `notification_key`, `read_at` and `updated_at`.
- The authenticated server session supplies the username. A client cannot mark notifications read on behalf of another account by sending an identity in the request body.

## Event identity

Read state is bound to an event-level key instead of only a course/exam identifier. A changed source event therefore becomes unread again: assignment reactivation/due change includes assignment timing, a new failed exam includes the latest failed record identity, PGY includes workflow status, retraining includes the required material-version set, and an edited announcement includes a content hash.

## API

- `GET /api/notification-states?key=...` returns read markers only for the authenticated user and requested bounded keys.
- `PATCH /api/notification-states` with `{"keys": [...], "read": true|false}` marks those keys read or unread for the authenticated user.
- Notification keys are validated, deduplicated and capped per request. Workflow records, grades and announcements are never mutated by these routes.

## UI

`static/notification-center-71.js` merges read markers into the existing canonical aggregation, shows an unread count, supports per-item read/unread toggles and “mark all read”, and keeps source-domain action links unchanged.
