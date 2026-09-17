/* Compatibility router after Teacher runtime convergence.
 *
 * Exam/category CRUD belongs to admin-question-bank.js + admin-question-panel.js
 * and admin-exam-settings.js. Question CRUD belongs to admin-question-actions.js
 * + admin-question-editor-ui.js. AI authoring belongs to admin-ai-questions.js.
 *
 * This file intentionally owns no UI, persistence, RBAC, or API orchestration.
 * It keeps cached/older assessment681* callers working for one compatibility
 * cycle and lazy-loads the unique advanced blueprint/analytics surface.
 */
(function () {
  'use strict';

  const advancedSrc = '/assessment-advanced-74.js?v=7400';
  let advancedPromise = null;

  function ensureAdvanced() {
    if (window.AssessmentAdvanced74) return Promise.resolve(window.AssessmentAdvanced74);
    if (advancedPromise) return advancedPromise;
    advancedPromise = new Promise((resolve, reject) => {
      const existing = document.querySelector('script[data-assessment-advanced-74]');
      if (existing) {
        existing.addEventListener('load', () => resolve(window.AssessmentAdvanced74), {once:true});
        existing.addEventListener('error', () => reject(new Error('進階評量工具載入失敗')), {once:true});
        return;
      }
      const script = document.createElement('script');
      script.src = advancedSrc;
      script.defer = true;
      script.dataset.assessmentAdvanced74 = '1';
      script.addEventListener('load', () => resolve(window.AssessmentAdvanced74), {once:true});
      script.addEventListener('error', () => reject(new Error('進階評量工具載入失敗')), {once:true});
      document.head.appendChild(script);
    }).finally(() => { if (!window.AssessmentAdvanced74) advancedPromise = null; });
    return advancedPromise;
  }

  async function openCanonicalAssessment() {
    await window.openAdminWorkspace?.('assessment');
    await window.renderAdminQuizCategories?.(true);
    const root = document.getElementById('admin-quiz-workspace');
    root?.classList.remove('hidden');
    root?.scrollIntoView({behavior:'smooth', block:'start'});
    return root;
  }

  async function route(tab = 'exams') {
    if (tab === 'blueprint' || tab === 'analytics') {
      await openCanonicalAssessment();
      const advanced = await ensureAdvanced();
      return advanced?.open?.(tab);
    }
    // "exams", "bank" and legacy "ai" all converge onto the canonical
    // category/question workspace. AI controls live inside each canonical
    // question panel rather than in a second assessment application.
    return openCanonicalAssessment();
  }

  window.assessment681Refresh = () => openCanonicalAssessment();
  window.assessment681Tab = tab => route(tab);
  window.assessment681SelectExam = async id => {
    await openCanonicalAssessment();
    const panel = document.getElementById(`qpanel-${id}`);
    if (panel?.classList.contains('hidden')) await window.toggleQuizQuestionsPanel?.(id);
    panel?.scrollIntoView({behavior:'smooth', block:'start'});
  };

  // Cached pages may still call these old drawer-oriented names. Do not revive
  // the retired drawer; route users to the single canonical management surface.
  window.assessment681OpenQuestion = () => openCanonicalAssessment();
  window.assessment681CloseQuestion = () => {};

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => { ensureAdvanced().catch(() => {}); }, {once:true});
  } else {
    ensureAdvanced().catch(() => {});
  }
})();
