# 課程指派＝課程、教材、考卷的唯一可見規則（2026-10-15）

## 規則

一個人只要被**指派**某門課程（個人、組別、全體人員任一種），且該課程為「已發布、啟用中、與此人同訓練區」，
就能看到這門課的**課程、教材、考卷**，不論這些內容屬於哪一組。

- 實作：`teacher_app/learning/access.py::assigned_course_grants`（舊名 `personal_course_grants` 保留為別名）。
- 套用處：`access.can_access_learning_item`、`content_audience.visible_to_user`、
  `courses/visibility.add_personally_assigned_courses|exams`。
- 課程與考卷清單只在「課程所屬組」與「學員自己的組」兩個畫面出現，不會出現在無關的第三組分頁（`requested_group`）。

## 例外（仍然看不到）

- 沒被指派的人（除教學／系統管理者的全域權限外）。
- 課程未發布、已停用，或訓練區與此人不同。
- 教材被設成「僅供老師製作使用」(`source_only`) 或已停用。
- 考卷若另外設定了「受測對象」名單，名單仍是額外的縮小條件。

## 「可見範圍」(本組限定／全科共用／指定組別) 現在管什麼

只管**沒有放進任何課程**的教材與題庫。放進被指派課程的教材，不再需要另外設可見範圍。

## 前端

`static/teaching.js`、`static/system-learner.js`：教材以 `group` 或 `ownerGroup` 配對目前組別
（伺服器會把別組教材的 `group` 改標成學員自己的組，真正擁有者在 `ownerGroup`）；
`assignedFromGroup` 的課程與考卷保留在畫面上。

## 測試

`tests/test_course_assignment_single_rule_20261015.py`（身分 × 指派方式 × 同組／跨組 × 例外）、
`tests/test_learner_cross_group_assigned_course_20261015.py`。
