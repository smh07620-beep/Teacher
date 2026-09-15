# Teacher 6.9 — Legacy Office download retirement

The legacy `/download/<slide_id>` route remains available for non-Office compatibility, but Office source files are no longer returned by normal teaching workflows.

For `.ppt/.pptx`, `.doc/.docx`, `.xls/.xlsx`, `.odp/.odt/.ods`:

- canonical `material.manage` and group scope are checked first;
- single-PDF materials redirect to `/material-preview/<id>`;
- older page/image previews return HTTP 409 with `previewRequired=true`, so the caller opens the normal material reader;
- the route never falls through to the original Office source handler.

This closes the legacy source-download path without changing learner material reading or non-Office management downloads.
