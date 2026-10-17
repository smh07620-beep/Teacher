# 學員少載入教師／管理程式：評估與計畫

**狀態：開關 `STUDENT_LEAN_ASSETS` 預設仍為關閉。2026-10-17 起 3 支補丁檔已併入擁有者檔案，`assets.STUDENT_LEAN_EXCLUDE` 為 67 支（學員頁 116 支 → 49 支）。** 第 2、3 批（admin-* 26 支、teacher-* 與其他後台 30 支）已用靜態引用檢查加上本機瀏覽器（學員帳號）驗證：課程頁、教材閱讀器、考卷作答／交卷／結果、各學習模組切換，無主控台錯誤；管理員帳號仍載入全部 116 支。仍保留不排除：training-command-center-71、learning-analytics-71、course-lifecycle-f2、pgy-workflow、product-convergence-101、review-links-66、teacher-persona-isolation-1014、teacher-media-audio/subtitle-1014、teacher-slide-narration-1109、notification-center-71 等學員畫面可能用到的檔案。正式開啟前請在 Render 預備環境以學員身分再跑一次完整流程。

## 為什麼

學習中心頁面（`/system`）每個人第一次都要下載 116 支 JS，壓縮後約 586 KB。其中名稱屬於教師／管理的 74 支約 422 KB，學員用不到。第一次載入的流量約 75% 是這些 JS。

## 為什麼不能只靠檔名過濾

盤點顯示，很多學員要用的程式會引用教師／管理程式裡定義的名稱；而名稱帶 `teacher-` 的程式也有學員要用的（例如 `teacher-slide-narration-1109.js` 提供學員的投影片講解）。必須逐支確認。

## 建議作法（上線穩定後）

1. 用 `python tools/student_asset_inventory.py` 重新產生下方清單（檔案會增減）。
2. 逐支確認「被其他程式引用的名稱」是否只在教師／管理畫面使用，或有 `typeof … === 'function'` 保護。
3. 在 `teacher_app/frontend/assets.py` 以**環境變數開關**（預設關閉）：學員角色的 `/system` 回應移除確認過的檔案。
4. 以學員身分跑完整 Playwright 測試與主控台錯誤檢查，全數通過才在 Render 開啟開關。
5. 先開一天觀察；出問題就關掉環境變數，立即回到現狀。

## 預期效果

首次載入再少約 400 KB（約 50%）；教師／管理者不受影響。

## 目前清單

| 檔案 | 壓縮後 KB | 名稱像教師/管理 | 被其他（學員）程式引用的名稱 |
|---|---:|:---:|---|
| `/course-wizard-681.js` | 32.7 | 是 | courseWizard681AddExternal, courseWizard681AddFiles, courseWizard681AttachAiProducts, courseWizard681Back, courseWizard681ChangeType, courseWizard681ConfirmType |
| `/worker-status-70.js` | 22.8 | 是 |  |
| `/system-learner.js` | 18.4 |  |  |
| `/teacher-media-script-1014.js` | 15.8 | 是 |  |
| `/teacher-content-studio-71.js` | 15.0 | 是 | className, innerHTML, openTeacherContentExam, renderFormalAtlas, switchAdminWorkspace |
| `/admin-course-material.js` | 14.0 | 是 | adminDeleteCourse, jumpToAdminQuiz, refreshAdminMaterialCourses, renderAdminCourseMaterialHub, renderAdminCourses |
| `/teacher-ai-material-1014.js` | 13.4 | 是 |  |
| `/admin-question-bank.js` | 12.4 | 是 | adminOpenExamPublish, adminQuickReviewExam, onAdminMaterialGroupChange, onAdminQuizGroupChange, refreshAdminMaterialCategoryOptions, renderAdminQuizCategories |
| `/teaching.js` | 12.1 |  |  |
| `/system-exam.js` | 11.8 |  |  |
| `/admin-material-upload.js` | 10.9 | 是 | adminUploadMaterials, deleteAdminMaterial, editAdminMaterial, prepareMaterialVersionUpload, publishMaterialVersion, toggleAdminMaterial |
| `/teacher-ai-media-controls-1023.js` | 10.7 | 是 | renderAdminCourseMaterialHub |
| `/teacher-ai-media-studio-1018.js` | 9.8 | 是 |  |
| `/teacher-slide-narration-1109.js` | 9.5 | 是 | __teacherNarrationRecording, openSlideViewer, presentationPreviewPageUrl |
| `/admin-exam-settings.js` | 8.8 | 是 | adminEditQuizCategory, adminToggleBlindMode, examPrimaryAction, previewCurrentExam, publishCurrentExam, reviewCurrentExam |
| `/admin-ai-questions.js` | 8.8 | 是 | adminGenerateAiQuestions, adminImportAiCandidates, aiGoBackToExam, aiGoReviewQuestions, filterAiMaterials, loadAiMaterialOptions |
| `/teacher-ai-video-1015.js` | 8.7 | 是 |  |
| `/teacher-content-composer-72.js` | 8.4 | 是 | className, innerHTML |
| `/teacher-assignment-experience-1014.js` | 8.0 | 是 |  |
| `/teacher-workspace-1014.js` | 7.8 | 是 | TeacherWorkspace1014 |
| `/pgy-workflow.js` | 7.6 | 是 |  |
| `/teacher-ai-presentation-1016.js` | 7.2 | 是 |  |
| `/admin-people.js` | 7.2 | 是 | adminSetProfileTag, adminSyncProfileTagChecks, closeAdminUserEditor, createAdminUserAccount, filterAdminUserAccounts, openAdminUserEditor |
| `/review-links-66.js` | 7.1 | 是 | teacher66OpenReviewSource |
| `/teacher-learners-p2.js` | 6.7 | 是 | renderAdminTable |
| `/atlas-annotations-1010.js` | 6.7 |  |  |
| `/teacher-media-audio-1014.js` | 6.6 | 是 |  |
| `/teacher-media-recorder-1014.js` | 6.6 | 是 |  |
| `/workspace-shell-70.js` | 6.5 |  |  |
| `/learner-study-exam-loop-1032.js` | 6.4 |  |  |
| `/teacher-action-queue-1024.js` | 6.1 | 是 | adminOpenExamPublish, openEssayReview, openTeacherContentExam, renderAdminCourseMaterialHub, renderAdminTable, renderMaterialJobs |
| `/material-upload-client.js` | 6.1 |  |  |
| `/teacher-ai-presentation-editor-f5.js` | 6.1 | 是 |  |
| `/admin-announcements.js` | 6.0 | 是 | createAdminAnnouncement, deleteAdminAnnouncement, escapeHtml, renderAdminAnnouncements, toggleAdminAnnouncement |
| `/admin-competency-matrix-92.js` | 6.0 | 是 |  |
| `/admin-question-editor-ui.js` | 5.9 | 是 | adminCancelInlineQuestionEditor, adminEditSelectedQuestions, adminInlineQuestionTypeChanged, adminSelectAllQuestions, adminToggleInlineQuestionEditor, adminUpdateQuestionSelection |
| `/teacher-assessment-inline-1031.js` | 5.7 | 是 |  |
| `/learner-narration-1100.js` | 5.5 |  |  |
| `/admin-jobs.js` | 5.2 | 是 | cancelMaterialJob, renderMaterialJobs, retryMaterialJob |
| `/teacher-ux-convergence-72.js` | 5.1 | 是 |  |
| `/teacher-ui-resilience-1014.js` | 5.1 | 是 | renderAdminQuizCategories, tagName |
| `/admin-system.js` | 5.0 | 是 | migrateLocalMaterialsToR2, renderAdminSystemStatus, renderStorageStatus |
| `/notification-center-71.js` | 4.9 |  |  |
| `/admin-question-actions.js` | 4.9 | 是 | adminAddQuizQuestion, adminBulkDeleteQuestions, adminBulkSetQuestionActive, adminBulkSetQuestionTag, adminDeleteQuizQuestion, adminImportQuizUrl |
| `/system-assessment.js` | 4.9 |  |  |
| `/atlas-docx-wizard-70.js` | 4.8 |  |  |
| `/teacher-media-subtitle-1014.js` | 4.8 | 是 | openMaterial |
| `/system-core.js` | 4.7 |  |  |
| `/rbac-ui-681.js` | 4.7 |  |  |
| `/content-audience-1014.js` | 4.6 |  |  |
| `/training-command-center-71.js` | 4.5 |  |  |
| `/assessment-advanced-74.js` | 4.4 |  |  |
| `/admin-workspace.js` | 4.4 | 是 | AdminWorkspaceShell, isAdminWorkspacePage, openAdminWorkspace, switchAdminWorkspace, toggleAdminModal |
| `/admin-materials.js` | 4.4 | 是 | invalidateAdminMaterialsCache, rebuildMaterialIndex, renderAdminMaterials |
| `/teacher-content-tool-panels-710.js` | 4.4 | 是 | loadAiMaterialOptions, loadQuizQuestionsIntoPanel, openAdminWorkspace, openTeacherContentExam, renderAdminQuizCategories, toggleQuizQuestionsPanel |
| `/teacher-content-latency-712.js` | 4.4 | 是 | openAdminWorkspace, renderAdminQuizCategories |
| `/admin-results-data.js` | 4.2 | 是 | adminResultDetail, clearAllRecords, renderAdminTable |
| `/admin-results-workspace.js` | 4.1 | 是 | renderAdminTable, switchTeacherMode |
| `/system-csp-actions.js` | 4.1 |  |  |
| `/atlas-70.js` | 4.0 |  |  |
| `/teacher-interface-convergence-1014.js` | 4.0 | 是 |  |
| ~~`/teacher-authoring-source-fix-1017.js`~~ | — | — | 2026-10-17 字幕來源選單併入 `/teacher-media-subtitle-1014.js`，其餘救援程式移除 |
| `/smart-learning-67.js` | 3.8 |  |  |
| `/training-intervention-f3.js` | 3.8 |  |  |
| `/admin-results-export.js` | 3.6 | 是 | exportRecordToWord, exportToCSV |
| `/maintenance-64.js` | 3.0 | 是 | renderAdminSystemStatus, renderStorageStatus |
| `/learning-analytics-71.js` | 3.0 |  |  |
| `/teacher-course-tracking-f2.js` | 2.9 | 是 |  |
| ~~`/teacher-media-source-fix-1014.js`~~ | — | — | 2026-10-17 移除（`teacher-ai-media-controls-1023.js` 為唯一來源選單） |
| `/pgy-competency-matrix-71.js` | 2.8 |  |  |
| `/roles-signing-66.js` | 2.8 | 是 |  |
| `/admin-compliance-91.js` | 2.8 | 是 |  |
| `/admin-slide-checkpoints-1011.js` | 2.7 | 是 | openSlideCheckpointEditor |
| `/teacher-persona-isolation-1014.js` | 2.6 | 是 |  |
| `/teacher-paper-template-manager-1014.js` | 2.6 | 是 |  |
| `/shared-core.js` | 2.5 |  |  |
| `/workspace-routes-1007.js` | 2.5 |  |  |
| `/admin-doc-templates.js` | 2.5 | 是 | adminDeleteDocTemplate, adminTriggerDocTemplateUpload |
| `/learner-slide-checkpoints-1011.js` | 2.3 |  |  |
| `/admin-scenario-question-1011.js` | 2.3 | 是 |  |
| `/product-convergence-101.js` | 2.3 |  |  |
| `/learner-hotspot-question-1010.js` | 2.2 |  |  |
| `/admin-hotspot-question-1010.js` | 2.2 | 是 |  |
| `/admin-question-panel.js` | 2.1 | 是 | adminCreateQuizCategory, adminDeleteQuizCategory, loadAiMaterialOptions, toggleQuizQuestionsPanel, updateManualQuestionType |
| `/learner-reading-progress-f2.js` | 2.1 |  |  |
| `/api-get-dedupe-1007.js` | 2.0 |  |  |
| `/production-readiness-f6.js` | 2.0 |  |  |
| `/admin-pgy-assessments.js` | 2.0 | 是 | adminDeletePgyTemplate, adminImportTslmEpa, adminTriggerPgyTemplateUpload, renderAdminPgyAssessments |
| `/teacher-media-help-1014.js` | 1.8 | 是 |  |
| `/course-wizard-runtime-fix-1014.js` | 1.7 | 是 | courseWizard681OpenCourse |
| `/course-lifecycle-f2.js` | 1.7 |  |  |
| `/system-bootstrap.js` | 1.6 |  |  |
| `/admin-results.js` | 1.6 | 是 | closeEssayReview, openEssayReview, submitEssayReview |
| `/system-admin-focus-1014.js` | 1.6 | 是 |  |
| `/learner-scenario-question-1011.js` | 1.6 |  |  |
| `/sensitive-elevation-69.js` | 1.4 |  |  |
| `/admin-quiz-materials.js` | 1.4 | 是 | closeQuizMaterialLinker, filterQuizMaterialLinker, loadAiMaterialOptions, openQuizMaterialLinker, saveQuizMaterialLinks |
| `/external-material-681.js` | 1.4 |  |  |
| `/course-wizard-group-fix-1014.js` | 1.3 | 是 |  |
| `/learner-progress.js` | 1.3 |  |  |
| `/portal-navigation-73.js` | 1.3 |  |  |
| ~~`/teacher-media-status-fix-1014.js`~~ | — | — | 2026-10-17 併入 `/teacher-media-mvp-status-1014.js` |
| `/teacher-media-mvp-status-1014.js` | 1.2 | 是 |  |
| `/teacher-ai-presentation-video-handoff-f5.js` | 1.2 | 是 |  |
| `/teacher-media-free-tts-1014.js` | 1.1 | 是 |  |
| `/worker-status-convergence-101.js` | 1.1 | 是 |  |
| `/api-client.js` | 0.9 |  |  |
| `/admin-external-media.js` | 0.9 | 是 | escapeHtml |
| ~~`/teacher-workspace-nav-fix-1014.js`~~ | — | — | 2026-10-17 併入 `/teacher-workspace-1014.js` |
| `/teacher-voice-catalog-1026.js` | 0.8 | 是 |  |
| ~~`/learner-content-audience-1014.js`~~ | — | — | 2026-10-17 併入 `/system-learner.js` |
| `/learner-ui-cleanup-71.js` | 0.7 |  |  |
| `/learner-result-chart.js` | 0.7 |  |  |
| ~~`/teacher-ai-material-convergence-1014.js`~~ | — | — | 2026-10-17 併入 `/teacher-ai-material-1014.js` |
| `/learner-exam-controls.js` | 0.6 |  |  |
| `/system-admin.js` | 0.4 | 是 |  |

合計 116 支、586 KB；名稱像教師/管理的 74 支、422 KB。
