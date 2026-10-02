# Product Convergence — 2026-10-01

## Why this phase exists

The repository has strong component, RBAC, security, Worker, API and regression coverage, but passing those checks does not prove that a human can complete a whole job from beginning to end. The recurring product symptom is therefore:

- individual APIs and modules pass tests;
- the UI exposes too many implementation concepts as separate destinations;
- a user can still encounter a broken or confusing end-to-end workflow;
- feature existence is being confused with feature completion.

This phase does **not** replace the current architecture. `teacher_app.factory.create_app()`, canonical server-side RBAC/scope, audit rules, session/CSRF protections, Worker ownership, R2 direct upload and existing compatibility layers remain authoritative.

## Product information architecture

The product converges toward four human-facing work areas:

1. **我的學習** — assigned courses, materials, due work, exams, progress and personal results.
2. **教學工作區** — course creation, material authoring/upload, assignment, teacher-owned media and paper output.
3. **評量工作區** — question authoring, exams, grading/review, teacher assessment and results.
4. **系統管理** — people/permissions, platform health, Worker/Job operations, backup and audit.

PGY, internal training, newcomer training and laboratory groups are training programs/scopes inside the product. They must not become independent copies of the same platform.

## First convergence decisions

| Existing capability | Product decision | Destination |
| --- | --- | --- |
| Course/material management | Keep | 教學工作區 → 教材與課程 |
| AI material authoring | Integrate | 教材流程內工具 |
| AI media/audio/video | Integrate | 教材流程內「延伸教學工具」 |
| Paper/Word export | Integrate | 教材/教師流程內「延伸教學工具」 |
| Question bank + exam authoring | Keep and combine | 評量工作區 |
| Grading / teacher review | Integrate | 評量流程內，不另佔主導覽 |
| Worker / Job status | Keep | 系統管理 → 系統健康與維運 |
| Backup / restore | Keep | 系統管理 → 系統健康與維運 |
| Audit | Keep | 系統管理 → 安全與稽核 |
| PGY / internal training / group centers | Keep as program/scope | 我的學習 / 教學內容分類 |
| Technical queue/provider state | Hide from normal users | Only expose human status first; technical detail on demand |

## Definition of Done for a feature

A feature is **Operational** only when all of the following are true:

- the intended role can discover the action from the correct workspace;
- server-side RBAC and resource scope are enforced;
- the primary write/read workflow completes end to end;
- progress, empty, failure and retry states are understandable to a non-technical user;
- leaving/reloading at a critical point cannot silently lose the user's work;
- the final artifact/result appears where the next role expects it;
- important writes create the existing required audit trail;
- at least one Golden Path test protects the workflow outcome, not only individual endpoints.

Prototype/Beta capabilities may remain in the repository, but they should not receive a primary navigation entry until they meet this definition.

## Golden Path suite

These are the product-level acceptance flows. A regression in any P0 path should block release even when lower-level unit/API checks pass.

### GP-01 Teacher publishes learning material (P0)

Teacher creates or opens a course → uploads a PDF/PPTX/Office material → browser stores source safely → Worker claims with compatible protocol → processing/publish completes → material is attached to the course → teacher sees `可使用` → assigned learner can see/open it.

Failure acceptance: Worker failure shows a human-readable reason; R2 staging remains reusable; retry does not require re-upload while retention is valid.

### GP-02 Teacher assigns a course (P0)

Teacher/group leader selects an allowed audience → backend validates course area/scope → assignment is persisted → only intended learners see the course → unauthorized cross-scope users do not.

### GP-03 Learner completes a course (P0)

Learner opens assigned course → reads required material → completion is recorded → learner progress changes → teacher sees the same completion state.

### GP-04 Assessment lifecycle (P0)

Teacher creates questions/exam → publishes → assigned learner submits → teacher reviews/grades → reviewer identity is server-derived → result is persisted and visible to the correct learner/teacher scope.

### GP-05 Material Worker failure and recovery (P0)

Material is queued → Worker reports a processing error → Job UI immediately reports recent Worker error/retry → original staging source remains available → retry succeeds → course receives material once without duplicate provider publication.

### GP-06 Worker offline recovery (P0)

Compatible Worker is offline → upload/job remains safely queued without false processing attempts → UI says it is waiting → Worker returns → claims and completes the same job.

An incompatible Worker may heartbeat for observability but must not claim work.

### GP-07 Dual-role persona isolation (P1)

One account with learner + teaching responsibilities can switch between 我的學習 and 教師工作區 without duplicate navigation, leaked system controls or changed server-side scope.

### GP-08 User/RBAC provisioning (P1)

Authorized administrator creates/updates a user role/scope → session/profile exposes canonical role/permissions → target user sees the correct workspace and cannot call unauthorized write/sign endpoints.

## Test strategy change

The existing regression suite remains valuable. The added product-level rule is:

- **contract/unit tests** prove components and security boundaries;
- **integration tests** prove Web/DB/Worker contracts;
- **Golden Path browser tests** prove the user-visible outcome across those components.

A green unit/API suite is no longer sufficient evidence to call a workflow complete.

## Current high-value convergence backlog

### P0 — do before adding major new features

- Reduce teacher primary navigation to `教材與課程` and `評量與出題`.
- Keep AI media and paper export as contextual tools inside teaching flow.
- Consolidate system infrastructure under `系統健康與維運`.
- Turn GP-01, GP-02, GP-04, GP-05 and GP-06 into browser/integration release gates.
- Normalize user-facing Job states to `等待處理 / 處理中 / 可使用 / 需要處理`; keep raw technical states in expandable diagnostics.
- Make all empty states answer: what happened, what the user should do next, and whether data is safe.

### P1

- One `需要我處理` queue for teachers: pending review, failed material, approaching due date, unpublished draft.
- One learner `我的待辦` source instead of separate module-specific badges.
- Consolidate progress/competency views so duplicate percentages/statuses have one source of truth.
- Add mobile Golden Path coverage for course/material/assessment completion.

### P2

- Revisit deferred teacher capabilities (`我的學員`, clinical skill evaluation, competency tracking, teaching analytics) only after P0 Golden Paths are operational.
- Promote Beta features to primary navigation only after meeting the Definition of Done.

### P3 — hospital production acceptance

- Make the ordinary teacher material-upload surface use the same completion gate as the course wizard: R2/direct receipt is only the first stage, and the teacher is told it is safe to leave only after every queued Material Worker job is formally `completed`.
- Surface hospital Worker protocol incompatibility inline during the upload wait. An incompatible Worker may heartbeat for diagnostics but must not claim new jobs; queued material remains safe until the Worker is upgraded.
- Keep R2 staging on retry/failure and tell the teacher to reprocess the existing job instead of blindly re-uploading the same file.
- Keep Web releases independent from the physical hospital checkout: a normal Web deployment must not silently overwrite the hospital Worker. Local Worker upgrades remain an explicit operator action followed by a Worker restart.

## Stage 1 implementation in this change

`static/product-convergence-101.js` is a presentation-only convergence layer loaded after the existing workspace/persona scripts. It intentionally reuses existing workspace functions instead of rebuilding architecture:

- teacher primary navigation: exactly two jobs (`教材與課程`, `評量與出題`);
- media production and paper export: contextual teaching tools;
- system navigation: `人員與權限`, `系統健康與維運`, `安全與稽核`;
- no RBAC decision moves to the browser and no legacy secret/key seam is introduced.

The next implementation stage is Golden Path release gating, beginning with GP-01/GP-05 because material upload/Worker reliability is the highest operational risk observed in real use.

## Full-stack Golden Path status (2026-10-02)

The material release gate now includes a real isolated S3-compatible R2 lane using the same canonical boto3 adapter and the canonical `teacher_app.worker.material_worker_entry` process.

- **GP-01 full-stack:** Chromium uploads through the real presigned direct-upload API → R2-compatible object storage → real material Worker claim/download/publish → provider publish receipt → database commit → R2 staging cleanup → Chromium observes the published material.
- **GP-06 full-stack:** the real Worker is stopped before a second Chromium upload → the same queued job and R2 staging object are verified while offline → the canonical Worker restarts → claims the same job → publishes the same material identity → staging is removed only after completion → Chromium observes the result.
- The loopback HTTP R2 endpoint exists only for the isolated CI fixture. Production R2 remains HTTPS; the canonical provider and CSP layers refuse non-loopback HTTP overrides.
- GP-02/GP-03/GP-04/GP-05 still retain their existing integration release gates; browser-level convergence for the remaining user workflows is tracked separately rather than being mislabeled as full-stack coverage.



## Phase A–E completion status (2026-10-02)

The convergence program is now release-gated instead of being tracked only as a planning list.

| Phase | Status | Release evidence |
| --- | --- | --- |
| **A — Feature Inventory** | **Complete** | `RC_FEATURE_UI_COVERAGE_MATRIX.md` is the exhaustive engineering inventory and `PRODUCT_FEATURE_INVENTORY_20261001.md` applies the product decisions `保留 / 重複 / 未完成 / 廢棄 / 隱藏`. Known learner duplicate writers were physically retired and recorded as completed deprecations. |
| **B — Information Architecture** | **Complete** | `PRODUCT_INFORMATION_ARCHITECTURE_20261001.md` limits the product to `我的學習 / 教學 / 評量 / 系統管理`; PGY, group, Worker and media capabilities are scopes/tools rather than extra platforms. |
| **C — Golden Paths** | **Complete** | GP-01–GP-08 are release gates. The material path includes real Browser → presigned R2-compatible object storage → canonical `material_worker` → database → Browser, plus the same-job Worker-offline recovery path. |
| **D — UX Convergence** | **Complete** | Learner, teacher/assessment and system surfaces use the shared `Overview / 需要處理 / 目前工作 / 歷史紀錄` product-section contract. Canonical command-center progress/todo/action queues own visible state; the old portal progress/todo writers and duplicate review shortcut were removed. |
| **E — Production Hardening** | **Complete** | Error recovery and bounded retry/stale recovery are protected; Worker queue depth/oldest wait/failure rate/average duration are observable; security-sensitive writes use append-only audit; normal Email notifications share canonical events; critical Worker-offline alerts are projected after 5–60 minute bounded thresholds and checked every 10 minutes for system admins; material/course hot paths emit latency metrics; mobile learner/browser regressions are release-gated. |

Required release validation remains four independent gates:

1. **Teacher release checks**
2. **Product Golden Path checks**
3. **Playwright UI checks**
4. **Windows Worker checks**

A future feature is not considered converged merely because one of these gates passes; changes must preserve the relevant product, browser, backend/security and local-Worker gates together.
