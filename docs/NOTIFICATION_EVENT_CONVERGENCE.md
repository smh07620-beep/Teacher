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


## Operational history and SLO baseline (0110)

Migration `0110-operational-metrics-history` adds two bounded operational-history tables:

- `operational_metric_snapshots`: one idempotent sample per 10-minute bucket, retained for 30 days;
- `operational_incident_events`: stable open/resolved transition history per Incident generation so MTTR and component-frequency metrics are not lost when an Incident later reopens.

The existing 10-minute operational-alert workflow is also the sampling clock. It synchronizes Incident state, persists Incident transitions, then records queue depth, oldest pending age, recent failure rate, completed-job duration, stalled-job count, Worker availability, and open-Incident count. A snapshot failure does not erase an already persisted Incident transition.

The system-admin Worker / Job workspace exposes a separate `GET /api/operational-metrics?window=24h|7d` endpoint and renders:

- sampled Worker availability;
- material terminal-job success rate from existing `material_jobs`;
- material P95 and average processing time plus change versus the previous equal window;
- average/max queue depth and maximum oldest-wait age;
- Incident opened/resolved counts and MTTR;
- most frequently opened Incident error codes;
- explicit sample coverage so partial history is never presented as a complete seven-day record.

Queue depth and Worker availability cannot be reconstructed truthfully for time before 0110 deployment, so the UI shows the first sample time and coverage percentage. Existing material completion/failure rows are still used for historical success/duration calculations.

Formal SLO targets are optional and deliberately have no product defaults. If the organization wants pass/fail target context, configure on the Web/Render environment:

```text
OPERATIONS_SLO_WORKER_AVAILABILITY_PERCENT=
MATERIAL_SLO_SUCCESS_PERCENT=
MATERIAL_SLO_P95_DURATION_SECONDS=
```

When these values are absent, the UI labels the view as a baseline and does not invent a target.


## Sustained trend anomaly and capacity analysis

The 0110 history is also used for conservative trend detection. This does **not** create or assume formal SLO targets. It only promotes sustained deterioration into the existing Incident lifecycle after enough evidence is present.

Default detection policy:

- Queue growth: at least 6 ten-minute samples, net growth of at least 3 jobs, the second half of the window remains higher than the first half, almost all sample-to-sample moves are non-decreasing, and oldest pending age reaches at least 600 seconds.
- Worker capacity pressure: Queue growth must already be confirmed, then either only one Worker is available or a multi-Worker pool loses at least one average active Worker during the same window. The message remains "possible capacity pressure"; it does not claim hardware is the cause until Worker/provider/conversion failures are excluded.
- Processing slowdown: compare two equal 6-hour windows, require at least 3 completed jobs in each, and require P95 to increase by at least 1.5x and at least 60 seconds.
- Incident-frequency growth: compare the most recent 24 hours with the previous 24 hours, require at least 3 opens for the same non-trend error code, and at least 2x the previous count (or 3 opens when the previous count was zero).
- Trend-generated Incidents are excluded from the incident-frequency source count so the detector cannot recursively amplify itself.

These signals reuse the existing Incident lifecycle, deduplication, acknowledgement/assignment/maintenance controls, Email policy and automatic recovery. If trend-history projection itself is unavailable, existing trend Incidents stay OPEN/unknown instead of being falsely marked recovered.

Optional tuning knobs are Web/alert-runtime configuration, not Worker configuration:

```text
OPERATIONS_TREND_MIN_SAMPLES=6
OPERATIONS_TREND_QUEUE_MIN_GROWTH=3
OPERATIONS_TREND_QUEUE_OLDEST_SECONDS=600
OPERATIONS_TREND_DURATION_WINDOW_HOURS=6
OPERATIONS_TREND_DURATION_MIN_JOBS=3
OPERATIONS_TREND_DURATION_RATIO=1.5
OPERATIONS_TREND_DURATION_MIN_DELTA_SECONDS=60
OPERATIONS_TREND_INCIDENT_WINDOW_HOURS=24
OPERATIONS_TREND_INCIDENT_MIN_COUNT=3
OPERATIONS_TREND_INCIDENT_RATIO=2.0
```

A single queue spike, one slow job, or one provider Incident is intentionally insufficient for a trend Incident.


## Capacity planning / Forecast

The SLO workspace now includes a capacity-planning model built from the existing 0110 history; no new migration or Worker protocol is required.

The model deliberately separates three quantities:

- **arrival rate**: material jobs created during the forecast window;
- **observed completions**: successfully completed jobs during the same window;
- **per-Worker service capacity**: derived from real completed-job duration rather than dividing by wall-clock time, so idle time does not incorrectly reduce capacity.

Two service scenarios are shown:

- **nominal**: one Worker's jobs/hour from the median completed-job duration;
- **conservative**: one Worker's jobs/hour from P95 completed-job duration.

The default forecast window is 6 hours. A model is only considered usable when it has a recent Worker/queue sample, at least three completed jobs and at least 50% of expected ten-minute samples. The workspace shows confidence and limitations instead of manufacturing a number when the evidence is insufficient.

Queue ETA is calculated from:

```text
net drain rate = estimated Worker capacity - recent job arrival rate
queue clear time = current backlog / positive net drain rate
```

The dashboard shows both current-Worker and **+1 Worker** scenarios. This is a planning simulation only. It never starts another Worker or changes infrastructure.

Capacity interpretation remains conservative:

- if a blocking Worker/storage/conversion/network/database Incident is OPEN, the forecast says to repair the dependency first;
- if the existing P95-conservative scenario still has positive net drain, current capacity is shown as clearing the Queue;
- if nominal clears but P95 does not, capacity is labeled borderline;
- if current capacity cannot drain the recent arrival rate but one additional Worker can, the UI states that the +1 Worker scenario would restore net drain;
- if even +1 Worker does not restore net drain, the model says that adding only one Worker is insufficient instead of recommending repeated scaling.

Default forecast evidence knobs are Web-side operational settings, not formal SLO targets:

```text
OPERATIONS_FORECAST_WINDOW_HOURS=6
OPERATIONS_FORECAST_MIN_COMPLETED_JOBS=3
OPERATIONS_FORECAST_MIN_SNAPSHOT_COVERAGE=0.5
```

These values control whether the model has enough evidence to calculate; they are not organizational performance targets.


## Workload-calibrated capacity model

The capacity Forecast now learns separate service-time distributions for distinct material workloads instead of treating every Job as equal.

Workload classes are derived only from existing persisted metadata:

- **document**: PDF / Office / text materials;
- **media**: video and audio;
- **image**: raster image uploads;
- **archive**: ZIP packages;
- **other**: any remaining supported material type.

For each class, the system uses real completed jobs to calculate median and P95 processing duration, recent arrival rate, current backlog count/bytes, and source-size bands (<10 MB, 10–100 MB, >=100 MB).

When available, existing Worker result metadata further calibrates the class:

- document results use persisted `pageCount` to show median pages and median processing seconds/page;
- media results use persisted `storageMeta.durationSeconds` and `mediaKind` to show median media duration and processing/media real-time ratio;
- source file bytes are used as evidence bands, not assumed to have a linear relationship with processing time.

A workload class needs at least two completed jobs by default before it is considered calibrated:

```text
OPERATIONS_FORECAST_MIN_WORKLOAD_COMPLETED_JOBS=2
```

The mixed workload model converts each class into Worker-hours of demand:

```text
arrival worker demand = arrival_rate × class service_time / 3600
backlog worker-hours = backlog_count × class service_time / 3600
mixed queue ETA = backlog worker-hours / (active Workers - arrival worker demand)
```

Both nominal (class median) and conservative (class P95) versions are shown for the current Worker pool and the +1 Worker simulation.

If any recent arrival or current backlog belongs to a workload class without enough completed samples, the mixed ETA is intentionally marked unavailable/partially calibrated. The previous all-Job Forecast remains visible as a fallback, but the UI explicitly says that the workload-aware model is incomplete. This prevents document performance from being applied to a long video without evidence.

No new migration is required because `material_jobs.original_name`, `source_bytes`, `result.pageCount`, and `result.storageMeta.durationSeconds` already exist.


## Peak workload Capacity What-if

The system-admin SLO workspace now provides a **read-only** peak-capacity simulator. It does not create material jobs, change queue priority, start a Worker, or write operational state.

The default mixed preset is intentionally concrete: 10 documents plus three 30-minute media files. Administrators can change:

- document count and average pages per document;
- media count and average media minutes;
- image count;
- ZIP/archive count.

Server-side input is bounded even though the form also has HTML limits:

```text
documents: 0–100
document pages: 1–500
media: 0–50
media minutes: 1–240
images: 0–100
archives: 0–50
```

Simulation uses the workload calibration already learned from real jobs:

- documents prefer median/P95 **seconds per page** when page metadata is available, otherwise the class median/P95 job duration;
- media prefer median/P95 **processing-to-media-duration ratio**, otherwise the class median/P95 job duration;
- image/archive workloads use their class service-time distribution.

A peak batch is added to the current calibrated backlog while recent workload arrival demand is assumed to continue. For each 1-Worker and 2-Worker scenario:

```text
net Worker-hours/hour = Worker count - background workload demand
peak service hours = current backlog service hours + injected peak service hours
clear ETA = peak service hours / positive net Worker-hours/hour
```

The output shows nominal and P95-conservative ETA, background utilization, peak backlog job count, and the workload responsible for the largest share of injected P95 Worker-hours.

The model intentionally refuses a combined ETA when any requested workload, recent arrival workload, or existing backlog workload is not calibrated. For example, a long video cannot inherit PDF service time merely because documents have many samples.

If a Worker/storage/conversion/network/database blocking Incident is open, calculations may still be shown as a planning reference, but the recommendation is explicitly **repair the dependency first**. The simulator never performs automatic scale-out.

API:

```text
GET /api/operational-capacity-simulation
```

It is session-authenticated and restricted to `system_admin`. It is GET/read-only so it does not require a mutation/CSRF workflow.


## Forecast prediction calibration (0111)

Migration `0111-forecast-prediction-calibration` adds `operational_forecast_predictions`, a bounded operational table for **pre-completion** service-time predictions and their later backtest results.

The integrity rule is deliberate: a prediction is created before the material Job finishes and is immutable thereafter. Completed jobs are then scored against `finished_at - started_at`. Failed/cancelled jobs are marked ignored instead of being treated as prediction misses.

Prediction capture has two paths:

- the Worker claim route records a best-effort prediction immediately so short PDF/Office jobs are not lost between ten-minute samplers;
- the ten-minute operational sampler also reconciles/evaluates predictions and backfills predictions for still-pending jobs that were not captured at claim.

The claim hook is fail-soft. Missing migration state, insufficient workload history, or prediction persistence failure never blocks Worker ownership or material processing.

The backtest stores no material content or filename. It retains only job id, workload class, size band, model basis/version, sample count, nominal/P95 predicted seconds, actual service time and error metrics. Evaluated rows are retained for 90 days.

Accuracy metrics are calculated over a rolling seven-day window:

- median absolute error seconds;
- median and mean absolute percentage error;
- signed median bias (optimistic / balanced / conservative);
- P95 coverage: fraction of real service times that were at or below the pre-completion P95 estimate;
- per-workload accuracy for document/media/image/archive/other.

Only real submitted jobs count. Capacity What-if inputs that were never actually uploaded are **not** backtest observations.

Forecast confidence uses backtest results only as a one-way safety adjustment. Stable accuracy does not upgrade a forecast whose snapshot/job coverage only justifies medium confidence. Poor real-world accuracy can downgrade confidence:

```text
OPERATIONS_FORECAST_ACCURACY_MIN_EVALUATED=5
OPERATIONS_FORECAST_ACCURACY_WARNING_ERROR_PERCENT=30
OPERATIONS_FORECAST_ACCURACY_HIGH_ERROR_PERCENT=50
OPERATIONS_FORECAST_ACCURACY_MIN_P95_COVERAGE_PERCENT=70
```

Defaults mean:

- fewer than five evaluated predictions: collecting only, no confidence adjustment;
- median absolute percentage error >= 30% or P95 coverage below 70%: lower confidence one level;
- median error >= 50% or materially lower P95 coverage: force confidence to low.

These are model-trust heuristics, not organizational SLO targets. The UI always shows both the raw evidence-based Forecast confidence and the post-backtest confidence when they differ.
