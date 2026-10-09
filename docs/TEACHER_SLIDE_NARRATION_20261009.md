# Teacher slide narration (老師旁白＋自動翻頁＋字幕)

Teachers can talk over a slide material in the normal viewer. The voice is stored as an
audio material and bound to the slide material with a page timeline. Learners then hear
the voice, the viewer turns pages in step, and teacher-approved captions are shown.

## Flow

1. Entry points exist **only in the material lists** (編輯課程 step 2 「本課程的教材」 and
   教材與課程總覽): the 「🎙 錄旁白／重錄旁白」 button calls
   `TeacherSlideNarration1109.open(material)`, which opens the viewer and arms the recorder
   (`static/teacher-slide-narration-1109.js`). Nothing is shown to learners or in the viewer
   otherwise. The same lists show a 「🎙 老師旁白」 badge and 「移除旁白」. The teacher then
   presses **開始錄製旁白** (reader mode `presentation` or `paged_document`).
   Only roles `clinical_teacher` / `group_leader` / `education_admin` with
   `material.manage` see it. A privacy reminder is confirmed before recording starts.
2. While recording, page changes are detected by polling `window.slideViewerState.index`
   (buttons, thumbnails and keyboard all count). Pause/resume is excluded from the timeline.
3. After stopping, the teacher previews the audio, then presses **儲存**:
   the file goes through the existing Browser → R2 → Worker upload lane (no media bytes
   through the Render Web process) and becomes an ordinary audio material.
4. `POST /api/materials/<source_id>/teacher-narration` binds it
   (`teacher_app/materials/teacher_narration_routes.py`).
5. Optionally the teacher queues an AI subtitle draft for the audio material through the
   existing `POST /api/media-subtitles/generate`; review and approval stay in
   「教材製作 → AI 字幕」. Learners only ever receive the **approved** version.
6. Learners: `learner-narration-1100.js` plays the voice when the material opens, follows
   the timeline (stops following when the learner turns a page by hand; a button resumes
   from the current page), and overlays approved captions (toggle remembered locally).

## Storage / schema

No new table or migration. The binding is stored in the audio material's `storageMeta`,
the same mechanism AI narration uses (`mediaKind` + `sourceMaterialId`):

```json
{
  "mediaKind": "teacher_narration",
  "sourceMaterialId": "<slide material id>",
  "sourceVersion": 2,
  "timeline": [{"page": 0, "startMs": 0}, {"page": 1, "startMs": 8200}],
  "durationMs": 61000,
  "boundBy": "<username>",
  "boundAt": "<iso timestamp>"
}
```

`service._attach_narrations` folds it into the slide material as `narration`
(`kind: "teacher"`, `timeline`, `durationMs`, `stale`). The audio material does not show up
as a separate learner material. `stale` is true when the slide material's version changed
after recording: the voice still plays but pages are no longer turned automatically.

## API: `POST /api/materials/<source_id>/teacher-narration`

Body: `{ "audioMaterialId": "...", "timeline": [{page, startMs}...], "durationMs": 61000 }`

Server-side checks (never trusts the browser): login; `material.manage` scoped to the
slide material's group; both materials exist, same group and training area; source is a
slide/preview material; audio is an audio material not used by AI narration or another
slide; timeline is non-empty, ≤ 600 entries, integer pages within the material's page
count, times non-decreasing and within the recording length. Audit event
`material.teacher_narration.bind`. Re-binding the same pair replaces the timeline.

## Known limits

* PDF materials that the viewer opens in continuous "document" mode have no page turning,
  so the recorder is not offered there.
* Re-recording creates a new audio material; the newest one is shown to learners, older
  ones stay in the admin material list until deleted.
* Subtitles are produced by the hospital AI Worker (local Whisper), so they depend on that
  computer being on; medical terms need the teacher's review before approval.
* Captions use the audio material's own audience rule, like AI narration does.
