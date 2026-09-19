# General audit events (migration 0077)

Migration `0077-general-audit-events` adds the canonical append-only
`audit_events` table for non-PGY administrative and security-sensitive actions.
The existing `pgy_assignment_audit` table remains the workflow-owned PGY audit
history; the administration audit workspace reads both sources as read-only
data.

The general event row stores the server-authenticated actor username and role,
action, target type/id, group/scope metadata, timestamp, and bounded JSON
before/after/detail snapshots. Audit serialization removes fields whose names
look like passwords, tokens, secrets, authorization/cookie/session data, or API
keys. Product routes must pass only the minimum metadata needed to reconstruct
what administrative action occurred.

`GET /api/audit/events` is the only general audit HTTP endpoint. It requires
the canonical `audit.read` capability, supports bounded filters, and exposes no
write/update/delete operation. The `auditor` role therefore remains strictly
read-only.

Current audited non-PGY actions include account creation/update and role
changes; assessment review/publish/delete; question review/delete and batch
delete plus immutable question-snapshot publication; AI generation submission and candidate import; material
publish/unpublish/delete; and backup export/restore. New security-sensitive
canonical write routes should append to the same store rather than introducing
a separate audit table.
