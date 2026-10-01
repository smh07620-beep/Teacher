# Notification event convergence

Actionable in-app notifications and scheduled email reminders share one read-only server projection:

- `GET /api/training-command-center/notifications`
- implementation: `teacher_app.notifications.events`
- canonical task source: `teacher_app.command_center.service.build_summary()`
- exam deadline source: server-authoritative `exam_windows`

The projection does not create a second authorization or completion model. Course completion, learner visibility, teacher review scope, Worker job visibility, and PGY workflow scope remain owned by their existing backend domains.

## Event/channel rules

`course`, `exam`, and teacher assignment `due` events are email-eligible only when their deadline is within `EMAIL_REMINDER_DAYS`. `retraining`, `review`, and `material_failure` are one-time email-eligible events. Other tasks remain in-app only. Platform announcements remain in-app informational items and are not included in scheduled email reminders.

Stable event keys are shared with `email_notification_log` so the scheduled sender does not resend the same event repeatedly. If SMTP delivery fails, the newly claimed keys are released so the next scheduled run may retry.

The browser Notification Center only persists personal read/unread state through the existing `GET/PATCH /api/notification-states` endpoints. It does not mutate task, course, assessment, Worker, or announcement state.
