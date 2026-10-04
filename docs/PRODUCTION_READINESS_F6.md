# F6 Production Readiness & Content Governance

F6 is the production-acceptance layer for the Teacher platform. It does not
replace the existing release gates. It adds a separate live-environment gate.

## Gate 1 — pre-deploy

The exact commit must pass:

- Teacher release checks
- Product Golden Path checks, including GP-09 and GP-10
- Playwright UI checks
- Windows Worker checks

A green CI commit is **not by itself** Production Ready.

## Gate 2 — post-deploy

After Render has deployed that exact `main` commit, a system administrator
opens the Worker / Job workspace and verifies **F6 Production Readiness**.

The read-only `GET /api/production-readiness` contract checks:

1. Render Web readiness and concrete deployment identity.
2. Production DB is PostgreSQL / Supabase.
3. Required migrations are applied.
4. Required deployment configuration is ready.
5. Browser and Worker have available shared storage.
6. At least one hospital Worker is online or busy.
7. Email reminder delivery health is visible; email delivery issues are warnings.
8. A logical backup can be built and has a SHA-256.
9. That backup passes a read-only restore rehearsal against the current schema.
10. Canonical DB/artifact reference integrity has no blocking broken references.

The UI only shows **PRODUCTION READY** when the live provider is Render and all
required post-deploy checks pass.

## Content change acceptance

Before publishing a new material/SOP version, the teacher UI calls
`GET /api/slides/<materialId>/impact` and shows:

- source-linked questions;
- affected exams and whether they are already published;
- published AI PowerPoint derivatives;
- published AI teaching videos;
- active course assignments;
- learners who previously completed that material;
- the number of learners that would require retraining.

Historical exam snapshots, prior material versions, and prior AI artifacts stay
immutable. A new material version never silently mutates them.

## Disaster recovery rehearsal

A backup download remains the portable logical archive. Before a real restore,
operators can POST the backup ZIP to
`/api/maintenance/restore/rehearsal` with confirmation `REHEARSE`.

Rehearsal is read-only. It reports table presence, compatible rows, skipped
rows, and source columns not present in the destination schema.

A real restore still requires the separate `RESTORE` confirmation.

## Integrity audit

`GET /api/maintenance/recovery-audit` is read-only and checks for:

- material-version rows whose canonical material no longer exists;
- AI derivative rows whose canonical material no longer exists;
- AI PowerPoints whose source material no longer exists;
- AI videos whose source PowerPoint no longer exists;
- questions whose source material no longer exists;
- learning assignments whose course no longer exists;
- R2 derivatives missing a live local R2 ledger observation.

R2 ledger gaps are warnings because the ledger is an observation layer.
Canonical DB-reference breaks are blocking errors.

## Operator sign-off

For an院內 production sign-off, retain evidence of:

- exact deployed commit;
- F6 Production Readiness = PRODUCTION READY;
- one teacher login and one learner login;
- Browser → R2 → Worker → published material;
- course assignment → learner completion;
- exam start → submit → result/review;
- PowerPoint generation/edit/approval;
- PowerPoint → video generation/approval/publication;
- material version impact preview;
- backup creation;
- restore rehearsal;
- recovery audit;
- Worker stop/restart recovery;
- mobile learner check.

Do not store credentials, tokens, database URLs, or real person-identifying
test data in acceptance evidence.
