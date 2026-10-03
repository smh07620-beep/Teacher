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


## Operational incidents (0108)

Migration `0108-operational-incidents` adds the small `operational_incidents` lifecycle table. It stores only operational state: incident key/type, severity, open/resolved status, generation, occurrence count, timestamps, bounded human detail/action, error code, and resource ID. It does not store material bytes, credentials, or authorization state.

The existing 10-minute `.github/workflows/worker-offline-alerts.yml` lane now synchronizes these incident conditions before email delivery:

- confirmed Worker offline after `MATERIAL_WORKER_OFFLINE_ALERT_SECONDS` (default 600 seconds);
- material job heartbeat beyond `MATERIAL_JOB_STALE_SECONDS`;
- a leading burst of the same storage/conversion error code, controlled by `MATERIAL_INCIDENT_ERROR_BURST_COUNT` (default 3);
- high recent material terminal failure rate when at least `MATERIAL_INCIDENT_FAILURE_RATE_MIN_JOBS` jobs exist (default 5) and the percentage reaches `MATERIAL_INCIDENT_FAILURE_RATE_PERCENT` (default 50).

An incident remains one row while the condition persists, so each system administrator gets one stable email event per incident generation. When the condition clears, the same row becomes `resolved` and produces one recovery event. If the condition later returns, generation increments and a new email key is produced. Worker-offline incidents are resolved only after a confirmed fresh heartbeat from the same physical worker identity; heartbeat retention expiry alone is never treated as recovery.

Operational incident and recovery email kinds are protected critical notifications, like existing material-failure/Worker-offline notifications. Ordinary learning email preferences cannot disable them. The Notification Center and Worker / Job status page reuse the same incident lifecycle instead of creating separate alert state.
