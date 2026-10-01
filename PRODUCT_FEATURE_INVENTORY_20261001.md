# Phase A — Product Feature Inventory

This document is the product-decision overlay for the exhaustive engineering
inventory in `RC_FEATURE_UI_COVERAGE_MATRIX.md`.

The RC matrix remains the single detailed list of product features, backend/runtime
owners, APIs/contracts, UI/callers, RBAC/scope and regression coverage. This file
adds the product disposition requested by Product Convergence without copying all
of those columns into a second list that can drift.

## Required product labels

Every current RC row receives exactly one product decision through this mapping:

| RC engineering status | Product decision | Meaning |
| --- | --- | --- |
| `Usable` | **保留** | Supported product capability. Keep one canonical entry/owner. |
| `Internal` | **隱藏** | Required runtime/technical capability, not a normal user surface. |
| `Compatibility` | **隱藏** | Temporary compatibility adapter only. It may remain callable but must not own business logic or normal navigation. |
| `Deferred` | **未完成** | Deliberately not promoted as a complete product workflow yet. |

Therefore every feature row already listed in `RC_FEATURE_UI_COVERAGE_MATRIX.md`
is classified. A new RC status may not be introduced unless this decision mapping
is updated in the same change.

## Explicit current duplicates — 重複

These are not separate product features. They are duplicate presentation writers
or legacy entry paths that still coexist with a canonical owner and must be
removed/converged rather than promoted:

| Duplicate | Canonical owner | Decision / next action |
| --- | --- | --- |
| `static/portal-v56.js` writes the learner progress card from `/api/dashboard/me` while `static/learning-progress-convergence-1025.js` owns the canonical progress projection | `/api/training-command-center/progress` + `learning-progress-convergence-1025.js` | **重複** — legacy write is compatibility fallback only; canonical projection must be the final visible owner and the old write should be retired during Phase D. |
| `static/portal-v56.js` can render its historical pending-course/exam block while `static/learner-todo-convergence-1025.js` owns the canonical learner todo projection | `/api/training-command-center` + `learner-todo-convergence-1025.js` | **重複** — canonical learner todo must always win; retire the old task writer during Phase D after browser gates prove parity. |
| Legacy root compatibility modules (`app.py`, `pgy_frontend.py`, `question_bank_68.py`, `free_worker_67.py`, `health_65.py`, `external_media_68.py`, `exam_integrity.py`) | `teacher_app.*` canonical packages and `teacher_app.frontend.assets` | **重複 / 隱藏** — keep only while compatibility callers exist; no new product ownership may be added. |

## Explicit retired surfaces — 廢棄

The following historical product surfaces are already retired and must not be
reintroduced:

- old assessment compatibility application/router;
- old question drawer/overlay;
- `pgy_atomic.py` redundant atomic patch layer;
- browser `getAdminKey()` / `X-Admin-Key` authorization seam;
- duplicate teacher/system daily-work navigation;
- persistent material executor as a normal daily teacher surface;
- PGY learner landing's former large management/admin list;
- homepage global search and duplicate top-level 課程 / 考核 navigation.

Their decision is **廢棄**. Compatibility tests may mention historical names only
to prove they remain absent.

## Explicit unfinished product work — 未完成

The following is intentionally not promoted to the primary Teacher product yet:

- 我的學員;
- 臨床技能評核 workspace expansion;
- 能力追蹤 as a separate teacher workflow;
- 教學分析 as a separate teacher workflow;
- any Beta/deferred capability that has not met the Product Convergence Definition
  of Done and an appropriate Golden Path.

These remain **未完成** even if lower-level backend primitives already exist.

## Explicit hidden technical surfaces — 隱藏

The following remain available only to the roles/workspaces that need them and
must not become normal learner/teacher navigation:

- raw provider credentials / SDK clients;
- Worker bearer token and local-worker protocol internals;
- raw queue stage, attempt counters, provider protocol version and low-level errors;
- background media conversion primitives;
- storage migration/maintenance internals;
- compatibility adapters listed above.

Human-facing status stays `等待處理 / 處理中 / 可使用 / 需要處理`; raw detail is
shown only on demand to authorized operational roles.

## Phase A completion rule

Phase A is complete only when all of the following stay true:

1. `RC_FEATURE_UI_COVERAGE_MATRIX.md` has no orphan product feature and records its
   backend owner, API/contract, UI/caller, RBAC/scope, regression and RC status.
2. Every RC status maps to exactly one of **保留 / 隱藏 / 未完成** above.
3. Every known duplicate presentation/entry owner is listed under **重複** until
   it is physically converged.
4. Retired surfaces are listed under **廢棄** and guarded by regressions where
   security or navigation could regress.
5. New product work updates both the RC inventory and, when its decision is an
   exception to the mapping, this overlay.

## Current Phase A status

**Operational, with the two portal duplicate writers explicitly carried into
Phase D cleanup.** The exhaustive inventory exists; the remaining Phase A work is
not discovery but closing those known duplicate presentation owners after Golden
Path parity is proven.
