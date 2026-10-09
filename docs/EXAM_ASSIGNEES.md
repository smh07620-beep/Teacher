# 考卷指定對象（exam assignees）

- 資料表：`exam_assignees(quiz_category_id, assignee_type, assignee_key, assigned_by, assigned_at)`，
  migration `0117-exam-assignees`（SQLite / PostgreSQL 皆相容、只新增、不改舊資料）。
- `assignee_type`：`user`（帳號）、`group`（組別代碼）、`all`（所有人）。
- 規則：考卷**沒有任何名單 = 維持原本行為**（範圍內所有人可見）；有名單 = 只有名單內的人與
  具 `exam.manage` 權限的管理者可見、可開始作答。
- 伺服器強制：`GET /api/quiz-categories`（學員清單）、學員儀表板待考清單、`exams.service.start_attempt`。
  已開始的作答不受後來名單變更影響。
- API：`GET|PUT /api/quiz-categories/<id>/assignees`（需 `exam.manage` 與該考卷所屬組別範圍；
  PUT 取代整份名單；每次變更寫入稽核事件 `assessment.assignees.update`，含前後名單）。
- 課程指派（`learning_assignments`）不會限制考卷；它只提供「個別指派者可看到課程」的授權。
