# AI question-generation jobs

AI question generation uses its own persistent queue. It does not reuse
`material_jobs`, because material processing and assessment authoring have
different payloads, permissions, retry semantics, and lifecycle ownership.

## Persistent state

Migration `0075-ai-question-jobs` creates `ai_question_jobs`. Each row stores:

- the assessment id, group and training-area scope captured when the request is accepted;
- the authenticated username that submitted the request;
- a normalized request snapshot containing material ids and generation options;
- `queued`, `processing`, `completed`, or `failed` status;
- persisted progress, result/error, timestamps, attempt count, and a private claim token.

Claiming is a conditional database update from `queued` to `processing`. A
second executor cannot claim the same row after the first update succeeds.
Progress, completion, and failure writes also require the claim token.

## HTTP contract

`POST /api/ai-questions/generate` validates the assessment/material scope,
normalizes the requested options, persists a job, and returns HTTP 202 with
`jobId`. The Web service does not execute the AI provider call.

`GET /api/ai-questions/jobs/<jobId>` requires the normal `question.manage`
permission and the persisted group scope. It exposes job status, progress,
timestamps, and the result only after completion. Internal request snapshots,
actor metadata, and claim tokens are not part of the response.

Generated candidates are not published questions. The admin UI requires a
separate human-reviewed import action; imported AI candidates enter the
question bank as drafts and must proceed through the existing review workflow.

## Dedicated worker

`ai_question_worker.py` is the only production execution owner. It polls the
database queue, atomically claims one queued row, writes progress/result state,
and periodically requeues stale `processing` rows. The worker composes the same
canonical `QuestionRuntime`, so provider behavior stays in
`teacher_app.assessments.ai_runtime` while HTTP remains owned by the Web app.

The Render Blueprint declares `biochemical-training-ai-worker` as a background
worker using the same lightweight Dockerfile as Web with a different command.
It therefore has MEGAcmd/storage read support but does not install FFmpeg or
LibreOffice. Video AI consumes Worker-produced `audio.m4a` / `poster.webp`, and
document AI prefers Worker-produced `index.txt`.

## Queue controls

The transitional executor supports these optional environment settings:

- `AI_QUESTION_JOB_MAX_ACTIVE_PER_USER` — active queued/processing jobs per user, default `3`.
- `AI_QUESTION_JOB_MAX_ACTIVE_TOTAL` — active jobs across the deployment, default `20`.
- `AI_QUESTION_JOB_MAX_PER_MINUTE` — accepted jobs per user per minute, default `6`.
- `AI_QUESTION_JOB_STALE_MINUTES` — processing age before startup recovery may requeue a job, default `20`.
- `AI_QUESTION_JOB_RECOVERY_LIMIT` — queued jobs scheduled during startup recovery, default `20`.
- `AI_QUESTION_WORKER_POLL_SECONDS` — dedicated worker queue poll interval, default `2`.
- `AI_QUESTION_WORKER_RECOVERY_SECONDS` — stale-job recovery interval, default `300`.

## Retrieval and provenance

Text and subtitle sources are split into stable chunks such as
`<materialId>:chunk-0001`. A bounded lexical retrieval step selects only the
chunks relevant to the requested focus/strategy instead of sending the entire
material text. The outbound prompt labels each selected chunk with
`sourceMaterialId` and `chunkId`.

Returned candidates are checked against those selected chunks. The server
derives a valid source when the model omits or invents an id, and stores the
result as `sourceMaterialId`, `chunkId`, `sourceEvidence`, plus
`answerConfig.reviewSource`. AI imports therefore preserve a human-review link
to the source material/chunk while remaining in draft status.
