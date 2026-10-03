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


## Incident response lifecycle (0109)

Migration `0109-operational-incident-response` keeps automatic detection state separate from human response state. The system remains the only authority that changes an Incident from `open` to `resolved`; a system administrator cannot manually hide an active failure.

For an OPEN Incident, a system administrator can:

- mark it acknowledged;
- assign it only to another active `system_admin` account;
- enter a bounded maintenance window from 15 minutes to 24 hours;
- add a bounded response note;
- clear maintenance or assignment without changing the automatic detection state.

Every response mutation is session/RBAC protected and is appended to the existing general audit log. A reopened Incident starts a new generation and resets response state, assignment, maintenance and note fields so an old acknowledgement cannot silently carry into a new outage.

While a maintenance window is active, the Incident remains visible in-app but new escalation Email is paused. Automatic recovery is never paused, and a recovery event remains Email-eligible. When the maintenance deadline expires, an unresolved Incident becomes escalation-eligible again.

The Worker / Job status page renders a static non-secret runbook selected by stable `errorCode` (for example `WORKER_OFFLINE`, `R2_STORAGE`, `FFMPEG_CONVERSION`, `LIBREOFFICE_CONVERSION`, `DATABASE`, DNS/network and AI failure-burst codes). Runbooks are guidance only; they do not execute infrastructure changes.
