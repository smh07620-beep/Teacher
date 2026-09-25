# 0084 Material Version + Retraining

This release adds version-aware training evidence for uploaded materials and SOPs.

## Rules

- Every uploaded material starts at **V1**.
- Publishing a new version always appends an immutable `material_versions` row.
- A minor revision can keep `required_completion_version` unchanged, so an earlier valid completion remains valid.
- A revision marked **requires retraining** moves `required_completion_version` to the new version. Older completion evidence remains stored but no longer satisfies the current training requirement.
- New completions snapshot the material version into `material_progress.completed_version` and Smart Learning `learning_progress.completed_version`.
- Dashboard and learner progress projections treat stale completion evidence as pending retraining instead of deleting it.

## Admin workflow

The material list shows the current version. **More → Publish new version** asks for a change reason and whether retraining is required. **Version history** shows the append-only publication history.

Publishing a version records `material.version.publish`. Revisions requiring retraining also record `material.retraining.require` in the general audit log.

## Compatibility

Migration `0084-material-version-retraining` is additive for SQLite and PostgreSQL. Existing materials and completion records are treated as V1, so deploying the migration does not invalidate historical training by itself.

This phase versions the canonical material record and training evidence. It does **not** create immutable historical copies of the underlying binary object; provider-level binary replacement/version retention remains a separate storage workflow.
