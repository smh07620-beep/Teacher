# Teacher 6.7 — Smart Learning Content

6.7 is additive and retains `pgy_app:app`, server-authoritative grading, answer-key/review-source protection, 6.6 signing, backup safety and legacy schemas. Migration `0067-smart-learning-content` adds learning progress, native text index, media jobs and preview-only DOCX/Atlas imports without deleting or overwriting data.

PPTX text is read from OOXML and PDF text from PyMuPDF; scanned PDFs report no searchable text. DOCX imports remain preview-first. Media processing requires a separately deployed durable worker; the web request never transcodes. FFmpeg is capability-detected and may be absent. Render worker deployment is documented only and has not been created.

ReviewSource 2.0 remains post-submit only and accepts legacy `timeSeconds` plus `timeStart`, `timeEnd` and bounded Atlas regions. Backups remain insert-missing-only.
