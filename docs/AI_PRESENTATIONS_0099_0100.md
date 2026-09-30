# AI PowerPoint 0099 / 0100 production hardening

This release turns the reviewed AI `slides` draft into a real `.pptx` artifact while preserving the existing Teacher RAG, AI Worker, RBAC, audit, and material publication boundaries.

## Data model

- `0099-ai-presentations` creates presentation templates, generation jobs, and presentation records.
- `0100-ai-presentation-production-hardening` upgrades an existing local-only 0099 deployment additively. It adds durable provider metadata, immutable revision lineage, and idempotent publication receipts. Existing rows are not replaced.

Apply normal Teacher schema migrations before enabling the feature on Web or the AI Worker.

## Durable provider requirement

Web and the dedicated AI Worker must point at the same durable provider. Configure `AI_PRESENTATION_STORAGE_BACKEND` to one of `r2`, `oci`, `gdrive`, or `mega`; `auto` selects the first configured shared provider in that order.

Local storage is fail-closed. It is only available when a single-host development environment explicitly sets:

```text
AI_PRESENTATION_STORAGE_BACKEND=local
AI_PRESENTATION_ALLOW_LOCAL_STORAGE=true
```

Do not enable local storage in a split Web/Worker deployment.

Any PowerPoint templates created by the earlier local-only 0099 prototype must be uploaded again after 0100 so that the Worker receives a durable provider key, checksum, byte size, and MIME type.

## Review and approval boundary

The source must be an existing AI material draft with `draftType=slides` and an explicit teacher approval record. Server-side group/area checks are repeated at enqueue and Worker execution time, including immutable revision re-renders.

Capabilities are explicit:

- `presentation.create`
- `presentation.edit`
- `presentation.approve`
- `presentation.publish`

`clinical_teacher` and `group_leader` may approve. `education_admin` and `system_admin` may create/edit and perform the operational publish step, but they deliberately do **not** receive teacher approval authority. Publication still fails closed until a clinical teacher or group leader has approved that exact presentation revision.

Every edit creates a new immutable revision. The original revision stays addressable. Structural edits never reuse the previous PPTX artifact: a new AI Worker render job must attach a fresh provider key/checksum/byte count/MIME tuple. Teacher-edited `.pptx` uploads are accepted only as valid macro-free Open XML presentations and are stored as another revision.

## Provenance

Generated PowerPoint core properties and writable speaker notes receive only allow-listed provenance identifiers: source material/draft/job/chunk ids, provider/model/template identifiers, and the teacher approval identity/time. Provider credentials, tokens, passwords, secret environment values, and local filesystem paths are rejected before the presentation is saved.

## Publication

Publishing is a separate operational action after teacher approval. The linked formal material must match the same group/area and already have a durable R2/OCI/Google Drive/MEGA location. The presentation artifact must also have a valid shared provider key, SHA-256, positive byte size, and the PPTX MIME type. Publication writes a deterministic receipt key so replaying the same presentation/material request is idempotent.

## Dependency boundary

`python-pptx` belongs to `requirements-ai-worker.txt`, not the Render Web dependency set. Web validates requests, creates immutable revisions, and enqueues work; only `ai_question_worker.py` renders PowerPoint files and uploads the generated artifact. The focused GitHub Actions check installs `python-pptx` separately so renderer regressions are exercised without adding the package to the production Web image.

## Deployment checklist

1. Deploy the Web and AI Worker code from the same revision.
2. Apply schema migrations including 0099 and 0100.
3. Install `requirements.txt` on Web and `requirements-ai-worker.txt` on the dedicated AI Worker; the latter installs `python-pptx`.
4. Configure the same `DATABASE_URL` and presentation storage provider on Web and AI Worker.
5. Re-upload any 0099 local-only PPT templates to shared storage.
6. Restart `ai_question_worker.py`; its queue loop consumes AI PowerPoint jobs alongside the existing AI/media queues.
7. Verify `/api/ai-presentations/status` reports a shared provider before enabling the UI.
8. Verify the `AI presentation production checks` workflow and the normal Teacher release checks are green before merging.

The next production phase can consume an **approved presentation revision** for narration/subtitles/video rendering; it must not bypass this teacher approval boundary.
