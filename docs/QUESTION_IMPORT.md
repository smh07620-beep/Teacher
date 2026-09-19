# Question import contract

This document describes the supported question-import behavior of the current canonical assessment runtime. It is part of the current `6.8.1` release contract even though the surrounding authoring UI carries later internal 7.x generation labels.

## Public JSON / CSV URL import

Endpoint: `POST /api/quiz-questions/import-url`

Request body:

```json
{
  "quizCategoryId": "category-id",
  "url": "https://example.org/questions.csv"
}
```

The caller must have `question.manage` permission for the target category scope. The target category must already exist.

The importer accepts only public `http://` or `https://` URLs. Before fetching, the hostname is resolved and every returned address is checked. Private, loopback, link-local, reserved and multicast destinations are rejected, so localhost, private networks and similar internal targets cannot be used as import sources. DNS resolution failure is reported before any fetch is attempted.

Remote content is limited to 5 MiB. JSON is selected when the response content type contains `json` or the URL path ends in `.json`; all other accepted responses are parsed as CSV. UTF-8 with an optional BOM is supported. JSON may be a top-level array or an object whose `questions` member is used. An object with no `questions` member is treated as an empty import; a non-list result is rejected.

At most the first 500 input rows are considered in one request. Import is row-tolerant: valid object rows are inserted, validation failures on object rows are skipped with messages, and non-object rows are ignored. The response includes at most 20 row errors.

Successful insertion marks the target assessment category as draft / review-invalidated. If no row is inserted, review state is not invalidated.

### Supported fields

The importer accepts English and selected Chinese aliases:

| Purpose | Accepted examples |
| --- | --- |
| Question text | `question`, `題目` |
| Type | `questionType`, `type`, `題型` |
| Options | `options` JSON/list, pipe-separated text, or `optionA` through `optionF` |
| Single answer | `correct`, `answer`; `A` through `F` are converted to zero-based indexes; true/false also accepts `是` / `否` |
| Multi-select answers | `answerConfig.correctIndices`, `correctIndices`, `正確選項` |
| Fill answers | `answerConfig.acceptedAnswers`, `acceptedAnswers`, `可接受答案`, `標準答案` |
| Difficulty | `difficulty`, `難度` |
| Tag/category label | `tag`, `分類` |
| Explanation | `explanation`, `詳解` |
| Image | `imageUrl` |
| Video metadata | `answerConfig.mediaUrl` / `mediaUrl` / `影片網址`, `answerConfig.pauseAt` / `pauseAt` / `時間點` |

Recognized type aliases include choice/single choice, multi-select, true/false (`true_false`, `truefalse`, `是非題`, `判斷題`), fill, essay, image and video. Unrecognized type strings fall back to `choice` for legacy compatibility.

Choice-like imported types (`choice`, `multi`, `image`, `video`) require at least two options. True/false questions always use `是` / `否`. For single-answer types, a supplied `correct` value must resolve to an existing option; malformed or out-of-range answers are rejected instead of being silently changed. Multi-select questions require at least one correct index. Fill questions require at least one accepted answer. Rows missing required content are skipped and reported.

### URL-import error contract

Validation/fetch failures return HTTP 400 with an `error` string. Current stable messages include:

- `找不到考題頁籤`
- `僅接受公開 HTTP/HTTPS 連結`
- `基於安全性，不允許讀取內網或本機網址`
- `無法解析該網址`
- `題庫檔案超過 5MB`
- `讀取或解析連結失敗：...`
- `JSON 格式需為題目陣列，或使用 questions 陣列`

A completed import request returns HTTP 200 even when some rows are rejected:

```json
{
  "ok": true,
  "imported": 3,
  "errors": ["第2題格式不足"],
  "reviewInvalidated": true
}
```

Row-level messages include `第N題格式不足`, `第N題缺少多選正確答案`, `第N題缺少填空可接受答案`, `第N題：正確答案格式錯誤`, `第N題：正確答案超出選項範圍`, and canonical question-validation errors prefixed with the row number.

## AI candidate import

Endpoint: `POST /api/ai-questions/import`

This endpoint imports teacher-reviewed AI candidates that were already generated in the authoring workflow. It does not fetch a remote URL.

The caller must have scoped `question.manage` permission. The category must exist and `questions` must be a non-empty list. At most the first 50 candidates are considered in one call. Non-object candidates are reported as row errors; valid objects are passed to the canonical bulk question insertion path. Bulk validation requires list-shaped options for option-based types, an in-range integer `correct` for single-answer types, list-shaped in-range `answerConfig.correctIndices` for multi-select, and list-shaped `answerConfig.acceptedAnswers` for fill questions. True/false candidates are normalized to `是` / `否` options.

Stable validation failures include:

- missing category: HTTP 404, `找不到考題頁籤`
- empty/non-list selection: HTTP 400, `請至少勾選一題`
- bulk validation/write failure: HTTP 400, `批次匯入失敗：...`

Current bulk-validation suffixes include `選項格式錯誤`, `正確答案格式錯誤`, `正確答案超出選項範圍`, `多選題正確選項格式錯誤`, `多選題正確選項超出選項範圍`, `多選題至少要設定一個正確選項`, `填空題可接受答案格式錯誤`, `填空題至少要設定一個可接受答案`, and `題目內容或選項不足`. The endpoint prefixes these with `批次匯入失敗：`.

A successful request returns `ok`, `imported`, up to 20 row `errors`, and the inserted `questions`.

## Operational guidance

For Google Sheets, publish a CSV view that is reachable without authentication. Private Google Drive, SharePoint, hospital intranet and other login-only/internal URLs are intentionally unsuitable for URL import because the server-side importer must reject private/internal network targets and does not act as an authenticated document client.

Import is additive. Review imported questions in the normal Question Bank UI before publication, especially rows whose type was normalized for compatibility or whose source data omitted optional metadata.
