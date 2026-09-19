# Runtime Ownership Map — Stage 5 historical record and current cutover status

Branch target: `feature/teacher-content-authoring-studio-72`

This file originally tracked the Stage 5 migration from the monolithic Flask host. That migration has since crossed the production composition boundary. The statements below describe the **current** repository state; older Stage 5 assumptions such as “`pgy_app.py` still imports `app.py`” are no longer valid.

Formal release SemVer remains `6.8.1`. Internal UI/convergence work currently carries `7.9 / RC79` markers. Those labels do not change the formal release contract unless `VERSION` is intentionally updated.

## Production composition — cutover complete

- `pgy_app.py` is the WSGI entrypoint and contains `app = create_app()` from `teacher_app`.
- `teacher_app.factory.create_app()` is the production composition root. It creates the Flask object, runs canonical bootstrap, registers canonical blueprints and production domain routes, and installs common error handlers.
- `teacher_app.factory` has no `legacy_host`, `LegacyBaseAdapter`, root `app.py`, or `runtime_from_owner` production dependency.
- Root `app.py` is only a historical import alias to `teacher_app.legacy_host`. It remains for old imports and isolated compatibility tests; production startup does not pass through it.
- `teacher_app.legacy_host` is therefore a compatibility/test surface, not the production composition owner.

This cutover is structurally protected by `tests/test_teacher_app_factory.py`, `tests/test_root_mirror_policy.py`, and the GitHub release workflow.

## Canonical production registration

`teacher_app.factory` directly registers the current production surfaces, including:

- schema/bootstrap, health, hardening, browser cache policy and AI privacy;
- canonical auth, request context, exam and PGY blueprints;
- materials catalog/delivery/jobs/templates/synchronous upload and storage administration;
- courses, assessments, exam records and PGY assessment routes;
- training audience, command center and dashboard;
- smart learning/progress and announcements;
- worker HTTP routes using the canonical worker web runtime;
- external media, Atlas, course bundle/follow-up, elevation/RBAC and Question Bank routes;
- the canonical question runtime built by `build_canonical_question_runtime()`.

The root WSGI file must stay free of domain registration and business behavior. New production registration belongs in `teacher_app.factory` or a canonical domain package called by the factory.

## Compatibility seams that remain intentionally isolated

Several packages still expose narrow runtime-owner compatibility adapters. They exist for legacy-style unit fixtures and compatibility registration calls. Production factory composition passes explicit canonical runtimes instead:

- `teacher_app.assessments.question_runtime.runtime_from_owner`
- `teacher_app.worker.web_runtime.runtime_from_owner`
- `teacher_app.materials.job_runtime.from_compat_owner`

These `runtime_from_owner(...)` / `from_compat_owner(...)` helpers must not become a route back to `teacher_app.legacy_host` in production. Structural tests enforce that the canonical factory does not use them.

Root `app.py` also remains import-compatible because older tests and operational compatibility code still import `app`. That alias is not evidence that production uses the legacy host.

## Current domain owners

| Domain | Current production owner | Compatibility note |
| --- | --- | --- |
| Application composition | `teacher_app.factory` | `pgy_app.py` is WSGI-only; root `app.py` is import compatibility only. |
| Auth / session / roles / scope | `teacher_app.auth.*`, `teacher_app.common.auth`, `teacher_app.common.scope` | Historical legacy delegates may remain for isolated compatibility tests. |
| Exams / attempts / grading / records | `teacher_app.exams.*` | Root adapters must not regain business logic. |
| PGY workflow / signing / assessments | `teacher_app.pgy.*` | Established URLs remain stable while canonical packages own behavior. |
| Materials / upload / jobs / templates | `teacher_app.materials.*` | Provider/runtime callbacks are injected explicitly by factory/runtime builders. |
| Courses / bundle / follow-up | `teacher_app.courses.*` | 0072/0073 schema ownership remains in canonical migrations. |
| Assessment configuration / question runtime | `teacher_app.assessments.*` | Question routes receive the canonical `QuestionRuntime` in production. |
| Storage providers / web runtime | `teacher_app.storage.*` | No second provider session/client should be introduced. |
| Worker Web protocol / queue | `teacher_app.worker.*` | `material_worker.py` remains the executable local worker loop. |
| Smart learning / progress | `teacher_app.learning.*` | Production registration is canonical. |
| Atlas | `teacher_app.atlas.*` | DOCX import and Atlas persistence stay canonical. |
| Maintenance / backup / migrations / health | `teacher_app.maintenance.*` | Production startup runs canonical bootstrap/migrations before domain registration. |

## Storage and worker boundary

The Web process and local/hospital worker remain separate deployment roles. Web-side storage/provider construction and state belong under `teacher_app.storage`; worker queue/protocol persistence belongs under `teacher_app.worker`. The executable local worker stays `material_worker.py` and must not be duplicated by a second poller or queue consumer.

Material upload and worker routes should consume explicit canonical runtime objects. Compatibility owner adapters may support old tests, but production factory wiring must remain explicit so storage credentials, filesystem paths and provider clients do not flow through the legacy host.

## Question runtime boundary

Production Question Bank registration passes `build_canonical_question_runtime()` directly from `teacher_app.factory`. The runtime owns AI provider/source generation seams, storage image behavior, progress storage and configured limits. `runtime_from_owner()` exists only for compatibility fixtures.

Public question-import behavior is documented in `docs/QUESTION_IMPORT.md`; import validation must continue to preserve RBAC/group scope, SSRF protection, bounded download size, per-row validation and review invalidation after successful inserts.

## Deletion / regression rule

When removing another compatibility seam:

1. establish or confirm the canonical owner;
2. wire production factory/routes directly to it;
3. preserve exact public URLs, endpoint names, RBAC/scope and error contracts;
4. run focused tests plus the full release gate;
5. add or retain a structural guard preventing production from re-acquiring the retired dependency;
6. only then delete the obsolete compatibility implementation.

Historical 6.5–6.7 architecture and the pre-factory-cutover narrative are preserved in `docs/archive/ARCHITECTURE_HISTORY.md`. They are release history, not the current production ownership contract.
