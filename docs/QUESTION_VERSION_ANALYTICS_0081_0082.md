# Question version history and version-aware item analytics

Teacher keeps the editable Question Bank row as the current working copy, while
published/history-sensitive identity is append-only.

## 0081 question version history

`question_versions` stores one immutable snapshot per `(question_id, version)`.
The snapshot hash covers semantic question content (prompt, answer/options,
explanation, media/reference metadata and instructional metadata). Workflow-only
state such as review status, reviewer identity, active/retired state and sort
order does not create a new content version.

Existing installations are backfilled with exactly one baseline snapshot at the
question's current version. Older versions that predate this migration are not
invented or reconstructed. New content edits increment the live row version and
append the new immutable snapshot. Review/return/retire actions do not increment
the version. Deleting the live Question Bank row does not delete historical
`question_versions` rows.

Publication and exam-attempt snapshots carry both `version` and `questionHash`,
so historical exams remain attributable to the exact content seen by learners.

## 0082 version-aware item analytics

New `question_attempt_analytics` rows also persist `question_version` and
`question_hash`. Existing analytics rows receive the compatibility defaults
`question_version=1` and an empty hash; they are deliberately not assigned a
fabricated historical content hash.

Analytics for current/new question versions calculate difficulty P,
discrimination D, exposure, average response time, distractor distribution and
distractor effectiveness from rows belonging to the same immutable version.

Blueprint `qualityMode=balanced` is opt-in. It does not exclude otherwise valid
questions or override topic/difficulty/cognitive quotas. Items with insufficient
data remain neutral. For sufficient data, a bounded weight combines difficulty
fit, discrimination, distractor effectiveness and exposure freshness. The
immutable blueprint snapshot records the policy version, weight and metrics used
for each selected question, making the selection explainable and auditable.

`qualityMode=off` remains the default and preserves the existing random/quota
selection behavior.
