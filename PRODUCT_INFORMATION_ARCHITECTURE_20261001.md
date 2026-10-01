# Phase B — Product Information Architecture

Teacher has exactly four human-facing product areas. Program, cohort and laboratory
group are scope filters inside these areas; they are not separate applications.

## 1. 我的學習

Purpose: everything a learner needs to know, continue, complete or review.

Canonical surfaces and capabilities:

- learner home / 今日學習 launchpad;
- 我的待辦 from the Training Command Center;
- assigned courses and course learning center;
- material/SOP reader and version-aware completion;
- exams, result review and failed-exam remediation;
- canonical learning progress;
- saved learning items;
- learning calendar / due dates;
- completion certificates;
- own course feedback;
- PGY learner tasks, PGY progress and learner-facing evidence when the account is
  explicitly in the PGY audience.

Rules:

- no management CRUD is duplicated here;
- no raw Worker/provider/queue state is exposed;
- `internal`, `pgy` and laboratory group keys select learning scope only;
- dual-role users return here through the learner persona without losing their
  server-side role set.

## 2. 教學

Purpose: teachers create, organize, publish and assign learning content.

Canonical surfaces and capabilities:

- 課程與教材 workspace;
- course creation / Course Wizard;
- material upload and background processing status;
- material catalog, metadata, version publishing and retraining trigger;
- external YouTube/Vimeo/hospital-CDN material authoring;
- teaching content authoring studio;
- AI-assisted presentation/script/audio/video/subtitle authoring as contextual
  course/material tools;
- course assignment to permitted audiences;
- learner-visible preview/readiness before publish;
- paper/Word retention/export tools as contextual teaching tools;
- teacher `需要我處理` items that concern course/material failures, deadlines or
  unpublished content.

Rules:

- Teacher primary navigation stays focused on course/material work; media and paper
  tools do not become extra top-level platforms;
- raw Worker internals belong to 系統管理, while teachers receive human job states;
- server scope remains authoritative for every create/update/publish/assign action.

## 3. 評量

Purpose: design assessments, review evidence and complete clinical evaluation work.

Canonical surfaces and capabilities:

- 評量與出題 workspace;
- assessment configuration, review and publication;
- Question Bank 2.0 draft/review/publish lifecycle;
- AI-assisted question candidates with teacher review before publish;
- exam blueprint snapshots;
- item analytics;
- exam result/review sources;
- teacher manual essay review, using server-derived reviewer identity and record
  resource scope;
- PGY clinical assessment/sign/countersign/finalize flows according to canonical
  role boundaries.

Rules:

- system administrators may operate platform data but never replace a clinical
  reviewer/signatory;
- learner-provided reviewer/group/score/signature fields never grant authority;
- clinical teacher assignment and group-leader group scope are enforced server-side;
- manual review is not promoted as another top-level product area.

## 4. 系統管理

Purpose: govern people, platform health, storage and accountability.

Canonical subareas:

### 人員與權限

- user/account provisioning;
- role and multi-role management;
- preferred area/group and training-audience profile fields;
- profile metadata administration without treating presentation fields as RBAC.

### 系統健康與維運

- Worker online/offline and compatibility status;
- material job operational diagnostics;
- storage health/budget/migration controls;
- backup/restore and advanced maintenance;
- external-media verification/availability operations.

### 安全與稽核

- append-only audit views;
- security/read-only oversight;
- sensitive elevation boundaries and operational traceability.

Rules:

- daily teaching/course/question work is not duplicated into system navigation;
- technical detail is collapsed/on-demand and restricted to authorized roles;
- system admin capabilities never imply clinical signing authority.

## Scope is not information architecture

The following names must never become a fifth product area:

- PGY;
- 院內教育訓練 / internal;
- 生化、鏡檢、血清、血庫、細菌、血液組;
- 新進人員 / cohort;
- Worker / R2 / MEGA / Google Drive / AI provider.

They are respectively program/audience, training area, group/cohort or technical
implementation. The active human job still belongs to one of the four areas above.

## Navigation contract

1. Learner persona starts from **我的學習**.
2. Teacher persona exposes only the focused teaching and assessment jobs needed for
   current work; contextual tools stay inside those workspaces.
3. System persona exposes platform governance only.
4. Auditor gets read-only oversight, not a parallel administration application.
5. A dual-role account switches persona without role mutation and without leaking
   system-only controls into learner/teacher surfaces.
6. New product features must declare one of the four areas in the Phase A inventory
   before they may receive normal navigation.

## Current Phase B status

**Operational.** Existing convergence assets and regressions already enforce focused
teacher/system navigation and learner-first portal behavior. This document is the
formal IA contract used to prevent future navigation drift while Phase C/D continue.
