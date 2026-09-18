# Teacher 6.7 WIP summary

- BASE_66_SHA: `5d735157bf121be02b00fa5b31474e33110423a1`
- Branch: `work/teacher-6.7-smart-learning-content` (local only)
- M1: `ecfc20dcf78a624014658f6c8622ebf185ec705e`
- M2: `b4a2fb9ab7bb195873f1632e37f16c5a7f1602e9`
- M3: `b2cde52d01ae8f8401a7749a644cf6bb688557ce`
- M4: `88ab841131daa07f254c5b3346e3cd42f9780379`
- M5: `f7ca5341f40a5c41b3ce0637c162b41368ce57f3`
- M6: `ebbda2eb0dea3eb3c5839154253925d3eb776140`
- M7: local HEAD at time of this summary.

Schema: additive `0067-smart-learning-content`: learning progress, text index, durable media job metadata, and Atlas import previews. Backup remains insert-missing-only.

Known limitations: FFmpeg is capability-detected; a separate durable Render worker is required for actual media transcoding and has not been deployed. DOCX complex floating/grouped/SmartArt/chart/OLE content stays in the source document with an explicit warning.

No GitHub push, Render deployment, or production database change has occurred.
